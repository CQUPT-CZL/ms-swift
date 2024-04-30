from typing import Any, Callable, Dict, List, Literal, Optional, Tuple, Union

import torch
from torch import nn
from transformers import PreTrainedModel, trainer
from trl import ORPOTrainer as HFORPOTrainer

from swift.llm.utils.template import Context, Template
from swift.llm.utils.utils import sort_by_max_length
from swift.utils import get_logger
from .callback import DefaultFlowCallbackNew, PrinterCallbackNew, ProgressCallbackNew
from .mixin import PushToMsHubMixin, SwiftMixin

logger = get_logger()


class ORPOTrainer(PushToMsHubMixin, SwiftMixin, HFORPOTrainer):

    def __init__(self, *args, template: Template, test_oom_error=False, **kwargs):
        self.template = template
        args.model_init_kwargs = args.get('model_init_kwargs', None)
        super().__init__(*args, **kwargs)
        train_ds_info = self.stat_dataset(self.train_dataset)
        val_ds_info = self.stat_dataset(self.eval_dataset)
        self.dataset_info = {'train_dataset': train_ds_info, 'val_dataset': val_ds_info}
        if test_oom_error:
            self.train_dataset = sort_by_max_length(self.train_dataset, 20000)
        # performance
        self.perf: Dict[str, Any] = {
            'gen_time': 0.,
            'gen_len': 0,
            'memory': {},
            'model': self.model.get_trainable_parameters() if hasattr(self.model, 'get_trainable_parameters') else None,
        }

    def train(self, *args, **kwargs) -> torch.Tensor:
        res = super().train(*args, **kwargs)
        for i in range(torch.cuda.device_count()):
            self.perf['memory'][f'cuda:{i}'] = f'{torch.cuda.max_memory_reserved(i)/1024/1024/1024:.2f}GiB'
        return res

    def concat_template(self, feature):
        query: Optional[str] = feature.get('query', None)
        system: Optional[str] = feature.get('system', None)
        history: List = feature.get('history', [])
        if system is None:
            if self.template.use_default_system:
                system = self.template.default_system
        else:
            assert self.template.prefix_has_system is not None, 'not support `system`'
        res_context_list: List[Context] = []
        compute_loss_idx: List[float] = []
        if system is None:
            assert self.template.prefix != self.template.prefix_has_system, f'template.prefix: {self.template.prefix}'
            prefix = self.template.prefix
        else:
            prefix = self.template.prefix_has_system
        self.template._concat_context_list(prefix, res_context_list, compute_loss_idx, system=system)
        for i, (q, r) in enumerate(history):
            self.template._concat_context_list(
                [
                    *self.template.prompt,
                    '{{RESPONSE}}',
                    *self.template.chat_sep  # noqa
                ],
                res_context_list,
                compute_loss_idx,
                query=q,
                response=r,
                round0=i)  # noqa
        self.template._concat_context_list(
            self.template.prompt, res_context_list, compute_loss_idx, query=query, round0=len(history))
        res_context_list, compute_loss_idx = self.template._simplify_context_list(res_context_list, compute_loss_idx)

        return res_context_list, feature['response'], feature['rejected_response'], compute_loss_idx

    def build_tokenized_answer(self, answer):
        tgt_input_ids = self.template._encode_context_list([answer], [1.0])[0]
        tgt_input_ids += self.template._encode_context_list(self.template.suffix, [1.0])[0]
        return dict(
            input_ids=tgt_input_ids,
            attention_mask=[1] * len(tgt_input_ids),
        )

    def tokenize_row(self, feature, model: Union[PreTrainedModel, nn.Module] = None) -> Dict:
        batch = {}
        if not self.is_encoder_decoder:
            prompt, chosen, rejected, loss_scale = self.concat_template(feature)

            prompt_tokens, _, _, _ = self.template._encode_context_list(prompt, loss_scale)
            prompt_tokens = {
                'input_ids': prompt_tokens,
                'attention_mask': [1] * len(prompt_tokens),
            }
            prompt_tokens = {f'prompt_{k}': v for k, v in prompt_tokens.items()}

            if not isinstance(chosen, str):
                raise ValueError(f'chosen should be an str but got {type(chosen)}')
            chosen_tokens = self.build_tokenized_answer(chosen)
            # Avoid tokenizing the prompt repeatedly.
            chosen_tokens.update(prompt_tokens)

            if not isinstance(rejected, str):
                raise ValueError(f'rejected should be an str but got {type(rejected)}')
            rejected_tokens = self.build_tokenized_answer(rejected)
            rejected_tokens.update(prompt_tokens)

            longer_response_length = max(len(chosen_tokens['input_ids']), len(rejected_tokens['input_ids']))

            # if combined sequence is too long, truncate the prompt
            for answer_tokens in [chosen_tokens, rejected_tokens, prompt_tokens]:
                if len(answer_tokens['prompt_input_ids']) + longer_response_length > self.max_length:
                    if self.truncation_mode == 'keep_start':
                        for k in ['prompt_input_ids', 'prompt_attention_mask']:
                            answer_tokens[k] = answer_tokens[k][:self.max_prompt_length]
                    elif self.truncation_mode == 'keep_end':
                        for k in ['prompt_input_ids', 'prompt_attention_mask']:
                            answer_tokens[k] = answer_tokens[k][-self.max_prompt_length:]
                    else:
                        raise ValueError(f'Unknown truncation mode: {self.truncation_mode}')

            # if that's still too long, truncate the response
            for answer_tokens in [chosen_tokens, rejected_tokens]:
                if len(answer_tokens['prompt_input_ids']) + longer_response_length > self.max_length:
                    for k in ['input_ids', 'attention_mask']:
                        answer_tokens[k] = answer_tokens[k][:self.max_length - self.max_prompt_length]

            # Create labels
            chosen_sequence_tokens = {
                k: chosen_tokens[f'prompt_{k}'] + chosen_tokens[k]
                for k in ['input_ids', 'attention_mask']
            }
            rejected_sequence_tokens = {
                k: rejected_tokens[f'prompt_{k}'] + rejected_tokens[k]
                for k in ['input_ids', 'attention_mask']
            }
            chosen_sequence_tokens['labels'] = chosen_sequence_tokens['input_ids'][:]
            _paddings = [self.label_pad_token_id] * len(chosen_tokens['prompt_input_ids'])
            chosen_sequence_tokens['labels'][:len(chosen_tokens['prompt_input_ids'])] = _paddings
            rejected_sequence_tokens['labels'] = rejected_sequence_tokens['input_ids'][:]
            _paddings = [self.label_pad_token_id] * len(rejected_tokens['prompt_input_ids'])
            rejected_sequence_tokens['labels'][:len(rejected_tokens['prompt_input_ids'])] = _paddings

            for k, toks in {
                    'chosen_': chosen_sequence_tokens,
                    'rejected_': rejected_sequence_tokens,
                    '': prompt_tokens,
            }.items():
                for type_key, tokens in toks.items():
                    if type_key == 'token_type_ids':
                        continue
                    batch[f'{k}{type_key}'] = tokens

        else:
            # encoder-decoder
            batch = super().tokenize_row(feature, model)

        return batch

    @staticmethod
    def stat_dataset(llm_dataset) -> Any:
        _token_len = []
        from datasets import Dataset as HfDataset
        from swift.utils.np_utils import stat_array
        if isinstance(llm_dataset, HfDataset):
            chosen = llm_dataset['chosen_input_ids']
            rejected = llm_dataset['rejected_input_ids']
            for cc, rr in zip(chosen, rejected):
                _token_len.append(max(len(cc), len(rr)))
        else:
            for d in llm_dataset:
                _token_len.append(max(len(d['chosen_input_ids']), len(d['rejected_input_ids'])))
        _, stat_str = stat_array(_token_len)
        logger.info(f'Dataset Token Length: {stat_str}')
        return stat_str


trainer.DEFAULT_PROGRESS_CALLBACK = ProgressCallbackNew
trainer.DEFAULT_CALLBACKS = [DefaultFlowCallbackNew]
trainer.PrinterCallback = PrinterCallbackNew
