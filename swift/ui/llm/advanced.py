import gradio as gr

from swift.ui.i18n import get_i18n_labels


def advanced():
    get_i18n_labels(i18n)
    with gr.Accordion(elem_id="advanced_param", open=False):
        with gr.Blocks() as block:
            with gr.Row():
                optim = gr.Textbox(elem_id='optim', lines=1, scale=20)
                weight_decay = gr.Textbox(elem_id='weight_decay', lines=1, scale=20)
                logging_steps = gr.Textbox(elem_id='logging_steps', lines=1, scale=20)
                lr_scheduler_type = gr.Textbox(elem_id='lr_scheduler_type', lines=1, scale=20)
                warmup_ratio = gr.Slider(elem_id='warmup_ratio', minimum=0.0, maximum=1.0, step=0.05, scale=20)
            with gr.Row():
                more_params = gr.Textbox(elem_id='more_params', lines=1, scale=20)


i18n = {
    "advanced_param": {
        "label": {
            "zh": "高级参数",
            "en": "Advanced params"
        },
    },
    "optim": {
        "label": {
            "zh": "Optimizer类型",
            "en": "The Optimizer type"
        },
        "info": {
            "zh": "设置Optimizer类型",
            "en": "Set the Optimizer type"
        }
    },
    "weight_decay": {
        "label": {
            "zh": "权重衰减",
            "en": "Weight decay"
        },
        "info": {
            "zh": "设置weight decay",
            "en": "Set the weight decay"
        }
    },
    "logging_steps": {
        "label": {
            "zh": "日志打印步数",
            "en": "Logging steps"
        },
        "info": {
            "zh": "设置日志打印的步数间隔",
            "en": "Set the logging interval"
        }
    },
    "lr_scheduler_type": {
        "label": {
            "zh": "LrScheduler类型",
            "en": "The LrScheduler type"
        },
        "info": {
            "zh": "设置LrScheduler类型",
            "en": "Set the LrScheduler type"
        }
    },
    "warmup_ratio": {
        "label": {
            "zh": "学习率warmup比例",
            "en": "Lr warmup ratio"
        },
        "info": {
            "zh": "设置学习率warmup比例",
            "en": "Set the warmup ratio in total steps"
        }
    },
    "more_params": {
        "label": {
            "zh": "其他高级参数",
            "en": "Other params"
        },
        "info": {
            "zh": "以json格式输入其他超参数",
            "en": "Input in the json format"
        }
    },
}