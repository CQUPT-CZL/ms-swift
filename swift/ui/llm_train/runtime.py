import collections
import os.path
import time
import webbrowser
from datetime import datetime
from typing import Dict, List, Tuple, Type

import gradio as gr
import matplotlib.pyplot as plt
import psutil
from gradio import Accordion, Tab
from transformers import is_tensorboard_available

from swift.ui.base import BaseUI
from swift.ui.llm_train.utils import close_loop, run_command_in_subprocess
from swift.utils import (TB_COLOR, TB_COLOR_SMOOTH, get_logger,
                         read_tensorboard_file, tensorboard_smoothing)

logger = get_logger()


class Runtime(BaseUI):

    handlers: Dict[str, Tuple[List, Tuple]] = {}

    group = 'llm_train'

    all_plots = None

    log_event = None

    sft_plot = [
        {
            'name': 'train/loss',
            'smooth': 0.9,
        },
        {
            'name': 'train/acc',
            'smooth': None,
        },
        {
            'name': 'train/learning_rate',
            'smooth': None,
        },
        {
            'name': 'eval/loss',
            'smooth': 0.9,
        },
        {
            'name': 'eval/acc',
            'smooth': None,
        },
    ]

    dpo_plot = [
        {
            'name': 'loss',
            'smooth': 0.9,
        },
        {
            'name': 'learning_rate',
            'smooth': None,
        },
        {
            'name': 'rewards/margins',
            'smooth': 0.9,
        },
        {
            'name': 'rewards/chosen',
            'smooth': 0.9,
        },
        {
            'name': 'rewards/rejected',
            'smooth': 0.9,
        },
        {
            'name': 'rewards/accuracies',
            'smooth': None,
        },
    ]

    locale_dict = {
        'runtime_tab': {
            'label': {
                'zh': '运行时',
                'en': 'Runtime'
            },
        },
        'tb_not_found': {
            'value': {
                'zh':
                'tensorboard未安装,使用pip install tensorboard进行安装',
                'en':
                'tensorboard not found, install it by pip install tensorboard',
            }
        },
        'running_cmd': {
            'label': {
                'zh': '运行命令',
                'en': 'Command line'
            },
            'info': {
                'zh': '执行的实际命令',
                'en': 'The actual command'
            }
        },
        'show_log': {
            'value': {
                'zh': '展示运行状态',
                'en': 'Show running status'
            },
        },
        'stop_show_log': {
            'value': {
                'zh': '停止展示运行状态',
                'en': 'Stop showing running status'
            },
        },
        'logging_dir': {
            'label': {
                'zh': '日志路径',
                'en': 'Logging dir'
            },
            'info': {
                'zh': '支持手动传入文件路径',
                'en': 'Support fill custom path in'
            }
        },
        'log': {
            'label': {
                'zh': '日志输出',
                'en': 'Logging content'
            },
            'info': {
                'zh': '如果日志无更新请再次点击"展示日志内容"',
                'en':
                'Please press "Show log" if the log content is not updating'
            }
        },
        'running_tasks': {
            'label': {
                'zh': '运行中任务',
                'en': 'Running Tasks'
            },
            'info': {
                'zh': '运行中的任务（所有的swift sft命令）',
                'en': 'All running tasks(started by swift sft)'
            }
        },
        'refresh_tasks': {
            'value': {
                'zh': '刷新运行时任务',
                'en': 'Refresh tasks'
            },
        },
        'kill_task': {
            'value': {
                'zh': '停止任务',
                'en': 'Kill running task'
            },
        },
        'tb_url': {
            'label': {
                'zh': 'Tensorboard链接',
                'en': 'Tensorboard URL'
            },
            'info': {
                'zh': '仅展示，不可编辑',
                'en': 'Not editable'
            }
        },
        'start_tb': {
            'value': {
                'zh': '打开TensorBoard',
                'en': 'Start TensorBoard'
            },
        },
        'close_tb': {
            'value': {
                'zh': '关闭TensorBoard',
                'en': 'Close TensorBoard'
            },
        },
    }

    @classmethod
    def do_build_ui(cls, base_tab: Type['BaseUI']):
        with gr.Accordion(elem_id='runtime_tab', open=False, visible=True):
            with gr.Blocks():
                with gr.Row():
                    gr.Textbox(
                        elem_id='running_cmd',
                        lines=1,
                        scale=20,
                        interactive=False,
                        max_lines=1)
                    gr.Textbox(
                        elem_id='logging_dir', lines=1, scale=20, max_lines=1)
                    gr.Button(elem_id='show_log', scale=2, variant='primary')
                    gr.Button(elem_id='stop_show_log', scale=2)
                    gr.Textbox(
                        elem_id='tb_url',
                        lines=1,
                        scale=10,
                        interactive=False,
                        max_lines=1)
                    gr.Button(elem_id='start_tb', scale=2, variant='primary')
                    gr.Button(elem_id='close_tb', scale=2)
                with gr.Row():
                    gr.Textbox(elem_id='log', lines=6, visible=False)
                with gr.Row():
                    gr.Dropdown(elem_id='running_tasks', scale=10)
                    gr.Button(elem_id='refresh_tasks', scale=1)
                    gr.Button(elem_id='kill_task', scale=1)

                with gr.Row():
                    cls.all_plots = []
                    for k in Runtime.sft_plot:
                        name = k['name']
                        cls.all_plots.append(gr.Plot(elem_id=name, label=name))

                cls.log_event = base_tab.element('show_log').click(
                    Runtime.update_log, [],
                    [cls.element('log')] + cls.all_plots).then(
                        Runtime.wait, [
                            base_tab.element('logging_dir'),
                            base_tab.element('running_tasks')
                        ], [cls.element('log')] + cls.all_plots)

                base_tab.element('stop_show_log').click(
                    lambda: None, cancels=cls.log_event)

                base_tab.element('start_tb').click(
                    Runtime.start_tb,
                    [base_tab.element('logging_dir')],
                    [base_tab.element('tb_url')],
                )

                base_tab.element('close_tb').click(
                    Runtime.close_tb,
                    [base_tab.element('logging_dir')],
                    [],
                )

                base_tab.element('refresh_tasks').click(
                    Runtime.refresh_tasks,
                    [base_tab.element('running_tasks')],
                    [base_tab.element('running_tasks')],
                )

                base_tab.element('kill_task').click(
                    Runtime.kill_task,
                    [base_tab.element('running_tasks')],
                    [base_tab.element('running_tasks')] + [cls.element('log')]
                    + cls.all_plots,
                    cancels=[cls.log_event],
                )

    @classmethod
    def update_log(cls):
        return [gr.update(visible=True)] * (len(Runtime.sft_plot) + 1)

    @classmethod
    def wait(cls, logging_dir, task):
        if not logging_dir:
            return [None] + Runtime.plot(task)
        log_file = os.path.join(logging_dir, 'run.log')
        offset = 0
        latest_data = ''
        lines = collections.deque(
            maxlen=int(os.environ.get('MAX_LOG_LINES', 50)))
        try:
            with open(log_file, 'r') as input:
                input.seek(offset)
                fail_cnt = 0
                while True:
                    try:
                        latest_data += input.read()
                    except UnicodeDecodeError:
                        continue
                    if not latest_data:
                        time.sleep(0.5)
                        fail_cnt += 1
                        if fail_cnt > 50:
                            break

                    if '\n' not in latest_data:
                        continue
                    latest_lines = latest_data.split('\n')
                    if latest_data[-1] != '\n':
                        latest_data = latest_lines[-1]
                        latest_lines = latest_lines[:-1]
                    else:
                        latest_data = ''
                    lines.extend(latest_lines)
                    yield ['\n'.join(lines)] + Runtime.plot(task)
        except IOError:
            pass

    @classmethod
    def show_log(cls, logging_dir):
        webbrowser.open(
            'file://' + os.path.join(logging_dir, 'run.log'), new=2)

    @classmethod
    def start_tb(cls, logging_dir):
        if not is_tensorboard_available():
            gr.Error(cls.locale('tb_not_found', cls.lang)['value'])
            return ''

        logging_dir = logging_dir.strip()
        logging_dir = logging_dir if not logging_dir.endswith(
            os.sep) else logging_dir[:-1]
        if logging_dir in cls.handlers:
            return cls.handlers[logging_dir][1]

        handler, lines = run_command_in_subprocess(
            'tensorboard', '--logdir', logging_dir, timeout=2)
        localhost_addr = ''
        for line in lines:
            if 'http://localhost:' in line:
                line = line[line.index('http://localhost:'):]
                localhost_addr = line[:line.index(' ')]
        cls.handlers[logging_dir] = (handler, localhost_addr)
        logger.info('===========Tensorboard Log============')
        logger.info('\n'.join(lines))
        webbrowser.open(localhost_addr, new=2)
        return localhost_addr

    @staticmethod
    def close_tb(logging_dir):
        if logging_dir in Runtime.handlers:
            close_loop(Runtime.handlers[logging_dir][0])
            Runtime.handlers.pop(logging_dir)

    @staticmethod
    def refresh_tasks(running_task=None):
        output_dir = running_task if not running_task or 'pid:' not in running_task else None
        process_name = 'swift'
        cmd_name = 'sft'
        process = []
        selected = None
        for proc in psutil.process_iter():
            try:
                cmdlines = proc.cmdline()
            except (psutil.ZombieProcess, psutil.AccessDenied,
                    psutil.NoSuchProcess):
                cmdlines = []
            if any([process_name in cmdline
                    for cmdline in cmdlines]) and any(  # noqa
                        [cmd_name == cmdline for cmdline in cmdlines]):  # noqa
                process.append(Runtime.construct_running_task(proc))
                if output_dir is not None and any(  # noqa
                    [output_dir == cmdline for cmdline in cmdlines]):  # noqa
                    selected = Runtime.construct_running_task(proc)
        if not selected:
            if running_task and running_task in process:
                selected = running_task
        if not selected and process:
            selected = process[0]
        return gr.update(choices=process, value=selected)

    @staticmethod
    def construct_running_task(proc):
        pid = proc.pid
        ts = time.time()
        create_time = proc.create_time()
        create_time_formatted = datetime.fromtimestamp(create_time).strftime(
            '%Y-%m-%d, %H:%M')

        def format_time(seconds):
            days = int(seconds // (24 * 3600))
            hours = int((seconds % (24 * 3600)) // 3600)
            minutes = int((seconds % 3600) // 60)
            seconds = int(seconds % 60)

            if days > 0:
                time_str = f'{days}d {hours}h {minutes}m {seconds}s'
            elif hours > 0:
                time_str = f'{hours}h {minutes}m {seconds}s'
            elif minutes > 0:
                time_str = f'{minutes}m {seconds}s'
            else:
                time_str = f'{seconds}s'

            return time_str

        return f'pid:{pid}/create:{create_time_formatted}' \
               f'/running:{format_time(ts-create_time)}/cmd:{" ".join(proc.cmdline())}'

    @staticmethod
    def parse_info_from_cmdline(task):
        for i in range(3):
            slash = task.find('/')
            task = task[slash + 1:]
        args = task.split('swift sft')[1]
        args = [arg.strip() for arg in args.split('--') if arg.strip()]
        all_args = {}
        for i in range(len(args)):
            space = args[i].find(' ')
            splits = args[i][:space], args[i][space + 1:]
            all_args[splits[0]] = splits[1]
        return all_args

    @staticmethod
    def kill_task(task):
        all_args = Runtime.parse_info_from_cmdline(task)
        output_dir = all_args['output_dir']
        os.system(f'pkill -9 -f {output_dir}')
        time.sleep(1)
        return [Runtime.refresh_tasks()] + [gr.update(value=None)] * (
            len(Runtime.sft_plot) + 1)

    @staticmethod
    def task_changed(task, base_tab):
        if task:
            all_args = Runtime.parse_info_from_cmdline(task)
        else:
            all_args = {}
        elements = [
            value for value in base_tab.elements().values()
            if not isinstance(value, (Tab, Accordion))
        ]
        ret = []
        for e in elements:
            if e.elem_id in all_args:
                if isinstance(e, gr.Dropdown) and e.multiselect:
                    arg = all_args[e.elem_id].split(' ')
                else:
                    arg = all_args[e.elem_id]
                ret.append(gr.update(value=arg))
            else:
                ret.append(gr.update())
        return ret + [gr.update(value=None)] * (len(Runtime.sft_plot) + 1)

    @staticmethod
    def plot(task):
        if not task:
            return [None] * len(Runtime.sft_plot)
        all_args = Runtime.parse_info_from_cmdline(task)
        tb_dir = all_args['logging_dir']
        fname = [
            fname for fname in os.listdir(tb_dir)
            if os.path.isfile(os.path.join(tb_dir, fname))
        ][0]
        tb_path = os.path.join(tb_dir, fname)
        data = read_tensorboard_file(tb_path)

        plots = []
        for k in Runtime.sft_plot:
            name = k['name']
            smooth = k['smooth']
            if name not in data:
                plots.append(None)
                continue
            _data = data[name]
            steps = [d['step'] for d in _data]
            values = [d['value'] for d in _data]
            if len(values) == 0:
                continue

            plt.close('all')
            fig = plt.figure()
            ax = fig.add_subplot()
            # _, ax = plt.subplots(1, 1, squeeze=True, figsize=(8, 5), dpi=100)
            ax.set_title(name)
            if len(values) == 1:
                ax.scatter(steps, values, color=TB_COLOR_SMOOTH)
            elif smooth is not None:
                ax.plot(steps, values, color=TB_COLOR)
                values_s = tensorboard_smoothing(values, smooth)
                ax.plot(steps, values_s, color=TB_COLOR_SMOOTH)
            else:
                ax.plot(steps, values, color=TB_COLOR_SMOOTH)
            plots.append(fig)
        return plots
