# Copyright (c) Alibaba, Inc. and its affiliates.
from swift.utils import get_logger
from .argument import (AppUIArguments, DeployArguments, EvalArguments, ExportArguments, InferArguments, PtArguments,
                       RLHFArguments, SftArguments, WebuiArguments, is_adapter, swift_to_peft_format)
from .client_utils import (compat_openai, convert_to_base64, decode_base64, get_model_list_client,
                           get_model_list_client_async, inference_client, inference_client_async)
from .protocol import (ChatCompletionMessageToolCall, ChatCompletionRequest, ChatCompletionResponse,
                       ChatCompletionResponseChoice, ChatCompletionResponseStreamChoice, ChatCompletionStreamResponse,
                       ChatMessage, CompletionRequest, CompletionResponse, CompletionResponseChoice,
                       CompletionResponseStreamChoice, CompletionStreamResponse, DeltaMessage, Function, Model,
                       ModelList, UsageInfo, XRequestConfig, random_uuid)
from .template import (DEFAULT_SYSTEM, TEMPLATE_MAPPING, History, KTOTemplateMixin, Prompt, RLHFTemplateMixin,
                       StopWords, Template, TemplateType, get_env_args, get_template, register_template)
from .utils import (LazyLLMDataset, LLMDataset, dataset_map, download_dataset, find_all_linears, find_embedding,
                    find_ln, get_time_info, history_to_messages, inference, inference_stream,
                    is_lmdeploy_available, is_megatron_available, is_quant_model, is_vllm_available,
                    limit_history_length, messages_join_observation, messages_to_history, print_example,
                    safe_tokenizer_decode, set_generation_config, sort_by_max_length, stat_dataset)

logger = get_logger()

try:
    if is_vllm_available():
        from .vllm_utils import (VllmGenerationConfig, get_vllm_engine, inference_stream_vllm, inference_vllm,
                                 prepare_vllm_engine_template)
        try:
            from .vllm_utils import LoRARequest
        except ImportError:
            # Earlier vLLM version has no `LoRARequest`
            logger.info('LoRARequest cannot be imported due to a early vLLM version, '
                        'if you are using vLLM+LoRA, please install a latest version.')
            pass
    else:
        logger.info('No vLLM installed, if you are using vLLM, '
                    'you will get `ImportError: cannot import name \'get_vllm_engine\' from \'swift.llm\'`')
except Exception as e:
    logger.error(f'import vllm_utils error: {e}')

try:
    if is_lmdeploy_available():
        from .lmdeploy_utils import (
            prepare_lmdeploy_engine_template,
            LmdeployGenerationConfig,
            get_lmdeploy_engine,
            inference_stream_lmdeploy,
            inference_lmdeploy,
        )
    else:
        logger.info('No LMDeploy installed, if you are using LMDeploy, '
                    'you will get `ImportError: cannot import name '
                    '\'prepare_lmdeploy_engine_template\' from \'swift.llm\'`')
except Exception as e:
    from swift.utils import get_logger
    logger = get_logger()
    logger.error(f'import lmdeploy_utils error: {e}')
