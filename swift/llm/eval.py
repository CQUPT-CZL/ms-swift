# Copyright (c) Alibaba, Inc. and its affiliates.
import dataclasses
import os
from typing import Any, Dict

import json
from llmuses.constants import DEFAULT_ROOT_CACHE_DIR
from llmuses.run import run_task

from swift.utils import get_logger, get_main
from ..utils.utils import split_str_parts_by
from . import EvalArguments
from .utils.model import dtype_mapping

logger = get_logger()


@dataclasses.dataclass
class ModelOutput:
    name: str = None

    cmd: str = None

    requirements: Dict[str, str] = dataclasses.field(default_factory=dict)

    args: Dict[str, Any] = dataclasses.field(default_factory=dict)

    memory: str = None

    train_time: float = None

    train_samples: int = None

    train_samples_per_second: float = None

    last_model_checkpoint: str = None

    best_model_checkpoint: str = None

    best_metric: Any = None

    global_step: int = None

    num_total_parameters: float = None

    num_trainable_parameters: float = None

    num_buffers: float = None

    trainable_parameters_percentage: float = None

    train_dataset_info: str = None

    val_dataset_info: str = None

    train_create_time: float = None


def parse_output(file):
    with open(file, 'r') as f:
        content = json.load(f)

    name = content['name']
    cmd = content['cmd']
    requirements = content['requirements']
    args = content['args']
    memory = content['memory']
    total_memory = 0.0
    for values in memory.values():
        total_memory += float(values.split('GiB')[0])
    memory = f'{total_memory}GiB'
    train_time = content['train_time']['train_runtime']
    train_samples = content['train_time']['n_train_samples']
    train_samples_per_second = content['train_time'][
        'train_samples_per_second']
    last_model_checkpoint = content['last_model_checkpoint']
    best_model_checkpoint = content['best_model_checkpoint']
    best_metric = content['best_metric']
    global_step = content['global_step']
    train_dataset_info = content['dataset_info']['train_dataset']
    val_dataset_info = content['dataset_info']['val_dataset']
    create_time = float(content['create_time'])
    # model_info like: SwiftModel: 6758.4041M Params (19.9885M Trainable [0.2958%]), 16.7793M Buffers.
    str_dict = split_str_parts_by(
        content['model_info'],
        ['SwiftModel:', 'M Params (', 'M Trainable [', ']), ', 'M Buffers.'])
    num_total_parameters = float(str_dict['SwiftModel:'])
    num_trainable_parameters = float(str_dict['M Params ('])
    num_buffers = float(str_dict[']), '])
    trainable_parameters_percentage = float(str_dict['M Trainable ['])

    return ModelOutput(
        name=name,
        cmd=cmd,
        requirements=requirements,
        args=args,
        memory=memory,
        train_time=train_time,
        train_samples=train_samples,
        train_samples_per_second=train_samples_per_second,
        last_model_checkpoint=last_model_checkpoint,
        best_model_checkpoint=best_model_checkpoint,
        best_metric=best_metric,
        global_step=global_step,
        train_dataset_info=train_dataset_info,
        val_dataset_info=val_dataset_info,
        train_create_time=create_time,
        num_total_parameters=num_total_parameters,
        num_trainable_parameters=num_trainable_parameters,
        num_buffers=num_buffers,
        trainable_parameters_percentage=trainable_parameters_percentage,
    )


def run_eval_full_model(model_id_or_path, dataset, generation_config,
                        model_args):
    eval_cfg = {
        'model_args': model_args,
        'generation_config': generation_config,
        'dataset_args': {},
        'model': model_id_or_path,
        'datasets': [dataset],
        'work_dir': DEFAULT_ROOT_CACHE_DIR,
        'outputs': DEFAULT_ROOT_CACHE_DIR,
        'mem_cache': False,
        'dataset_hub': 'ModelScope',
        'dataset_dir': DEFAULT_ROOT_CACHE_DIR,
        'stage': 'all',
        'limit': None,
        'debug': False
    }

    run_task(task_cfg=eval_cfg)


def llm_eval(args: EvalArguments) -> None:
    assert bool(args.model_id_or_path) ^ bool(args.ckpt_dir) ^ bool(args.exp_dir), \
        'Please pass either model_id_or_path or ckpt_dir or exp_dir'
    dtypes = {value: key for key, value in dtype_mapping.items()}
    if args.exp_dir is not None:
        outputs = []
        for dirpath, dirnames, filenames in os.walk(args.exp_dir):
            for file in filenames:
                if file.endswith('.json'):
                    outputs.append(parse_output(os.path.join(dirpath, file)))
        run_eval_single_task()
    elif args.model_id_or_path is not None:
        for ds in args.eval_dataset:
            run_eval_full_model(
                args.model_id_or_path,
                ds,
                generation_config={
                    'do_sample': args.do_sample,
                    'top_p': args.top_p,
                    'top_k': args.top_k,
                    'max_new_tokens': args.max_new_tokens,
                    'temperature': args.temperature,
                    'num_beams': args.num_beams,
                },
                model_args={
                    'device_map': 'auto',
                    'precision': dtypes[args.dtype] if args.dtype != 'AUTO' else dtypes['fp16'],
                })
    elif args.ckpt_dir is not None:
        run_eval_single_task()


eval_main = get_main(EvalArguments, llm_eval)
