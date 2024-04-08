# Copyright (c) Alibaba, Inc. and its affiliates.
import os

import json
import time
from tqdm.auto import tqdm
from transformers.trainer_callback import (DefaultFlowCallback,
                                           ProgressCallback, TrainerCallback,
                                           TrainerControl, TrainerState)
from transformers.trainer_utils import IntervalStrategy, has_length, speed_metrics

from swift.utils import is_pai_training_job
from .arguments import TrainingArguments


class ProgressCallbackNew(ProgressCallback):

    def on_train_begin(self, args, state, control, **kwargs):
        if state.is_local_process_zero:
            self.training_bar = tqdm(
                desc='Train', total=state.max_steps, dynamic_ncols=True)
        self.current_step = 0
        self.warmup_start_time = 0
        self.warmup_metric = None
        self.metric_warmup_step = int(args.metric_warmup_step * state.max_steps)if args.metric_warmup_step < 1 else args.metric_warmup_step

    def on_prediction_step(self,
                           args,
                           state: TrainerState,
                           control,
                           eval_dataloader=None,
                           **kwargs):
        if state.is_local_process_zero and has_length(eval_dataloader):
            if self.prediction_bar is None:
                if self.training_bar is not None:
                    self.training_bar.fp.write('\n')
                self.prediction_bar = tqdm(
                    desc='Val',
                    total=len(eval_dataloader),
                    leave=True,
                    dynamic_ncols=True,
                    position=0)
            self.prediction_bar.update()

    def on_log(self,
               args: TrainingArguments,
               state: TrainerState,
               control,
               logs=None,
               **kwargs):
        logs['global_step'] = state.global_step
        if state.global_step >= self.metric_warmup_step and self.warmup_start_time == 0:
            self.warmup_start_time = time.time()
            self.metric_warmup_step = state.global_step
        if state.max_steps == state.global_step and self.warmup_metric is None:
            num_steps = state.max_steps - self.metric_warmup_step
            # num_total_samples = int(logs['train_samples_per_second'] * logs['train_runtime'])
            num_total_samples = args.train_dataset_sample
            num_train_samples = int(num_total_samples / state.max_steps * num_steps)
            # num_train_samples = (state.max_steps - self.metric_warmup_step) * args.train_batch_size * args.gradient_accumulation_steps * args.world_size
            self.warmup_metric = speed_metrics(
                "warmup_train",
                self.warmup_start_time,
                num_train_samples,
                num_steps
                )
            self.warmup_metric['num_total_samples'] = num_total_samples
            self.warmup_metric['num_after_warmup_samples'] = num_train_samples
        if "train_samples_per_second" in logs:
            logs.update(self.warmup_metric)
            state.log_history[-1] = logs
        for k, v in logs.items():
            if isinstance(v, float):
                logs[k] = round(logs[k], 8)
        if not is_pai_training_job() and state.is_local_process_zero:
            jsonl_path = os.path.join(args.output_dir, 'logging.jsonl')
            with open(jsonl_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(logs) + '\n')
        super().on_log(args, state, control, logs, **kwargs)
        if state.is_local_process_zero and self.training_bar is not None:
            self.training_bar.refresh()


class DefaultFlowCallbackNew(DefaultFlowCallback):

    def on_step_end(self, args: TrainingArguments, state: TrainerState,
                    control: TrainerControl, **kwargs):
        control = super().on_step_end(args, state, control, **kwargs)
        # save the last ckpt
        if state.global_step == state.max_steps:
            if args.evaluation_strategy != IntervalStrategy.NO:
                control.should_evaluate = True
            if args.save_strategy != IntervalStrategy.NO:
                control.should_save = True
        return control


class PrinterCallbackNew(TrainerCallback):

    def on_log(self, args, state, control, logs=None, **kwargs):
        logs['global_step'] = state.global_step
        for k, v in logs.items():
            if isinstance(v, float):
                logs[k] = round(logs[k], 8)
        if not is_pai_training_job() and state.is_local_process_zero:
            jsonl_path = os.path.join(args.output_dir, 'logging.jsonl')
            with open(jsonl_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(logs) + '\n')

        _ = logs.pop('total_flos', None)
        if state.is_local_process_zero:
            print(logs, flush=True)

class ProfCallback(TrainerCallback):
    def __init__(self, prof):
        self.prof = prof

    def on_step_end(self, args, state, control, **kwargs):
        self.prof.step()