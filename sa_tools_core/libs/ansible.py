# coding: utf-8

from __future__ import absolute_import, print_function

import shutil
import logging
import ansible

ansible_version = ansible.__version__.split('.')  # NOQA

# if ansible_version < (2, 0, 0):
#     import ansible.utils.template  # NOQA
#     from ansible import errors  # NOQA
#     from ansible.callbacks import DefaultRunnerCallbacks  # NOQA
#     from ansible.inventory import Inventory  # NOQA
#     from ansible.runner import Runner  # NOQA
# else:

from ansible.module_utils.common.collections import ImmutableDict
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.inventory.manager import InventoryManager
from ansible.inventory.host import Host
from ansible.playbook.play import Play
from ansible.executor.task_queue_manager import TaskQueueManager
from ansible.plugins.callback import CallbackBase
from ansible import context
import ansible.constants as C  # NOQA

from sa_tools_core.consts import ANSIBLE_INVENTORY_CONFIG_FILES

logger = logging.getLogger(__name__)

loader = DataLoader()  # Takes care of finding and reading yaml, json and ini files

# create inventory, use path to host config file as source or hosts in a comma separated string
inventory = InventoryManager(loader=loader, sources=ANSIBLE_INVENTORY_CONFIG_FILES)

Inventory = lambda: inventory  # NOQA

# variable manager takes care of merging all the different sources to give you a unified view of variables available in each context
variable_manager = VariableManager(loader=loader, inventory=inventory)


class DefaultRunnerCallbacks(CallbackBase):
    '''
    make ansible 2.x Callback be compatible with ansible 1.9
    '''
    def __init__(self):
        self.results = {'contacted': {}, 'dark': {}}
        super(DefaultRunnerCallbacks, self).__init__()

    def v2_runner_on_failed(self, result, ignore_errors=False):
        super(DefaultRunnerCallbacks, self).v2_runner_on_failed(result, ignore_errors)
        host = result._host.get_name()
        self.results['contacted'][host] = result._result
        self.on_failed(host, result._result, ignore_errors)

    def v2_runner_on_ok(self, result):
        super(DefaultRunnerCallbacks, self).v2_runner_on_ok(result)
        host = result._host.get_name()
        self.results['contacted'][host] = result._result
        self.on_ok(host, result._result)

    def v2_runner_on_skipped(self, result):
        super(DefaultRunnerCallbacks, self).v2_runner_on_skipped(result)
        host = result._host.get_name()
        self.results['dark'][host] = result._result
        self.on_skipped(host, self._get_item_label(getattr(result._result, 'results', {})))

    def v2_runner_on_unreachable(self, result):
        super(DefaultRunnerCallbacks, self).v2_runner_on_unreachable(result)
        host = result._host.get_name()
        self.results['dark'][host] = result._result
        self.on_unreachable(host, result._result)

    def v2_playbook_on_no_hosts_matched(self):
        super(DefaultRunnerCallbacks, self).v2_playbook_on_no_hosts_matched()
        self.on_no_hosts()

    def on_failed(self, host, res, ignore_errors=False):
        pass

    def on_ok(self, host, res):
        pass

    def on_skipped(self, host, item=None):
        pass

    def on_unreachable(self, host, res):
        pass

    def on_no_hosts(self):
        pass


class Runner(object):
    def __init__(self, module_name='shell',
                 module_args=None,
                 become=False,
                 callbacks=None,
                 run_hosts=None,
                 forks=1):
        self.callback = callbacks

        if not isinstance(run_hosts, list):
            run_hosts = [run_hosts]
        run_hosts = [h.name if isinstance(h, Host) else h for h in run_hosts]

        # since the API is constructed for CLI it expects certain options to always be set in the context object
        # TODO: module_path?
        context.CLIARGS = ImmutableDict(connection='paramiko_ssh', module_path=['/to/mymodules'],
                                        forks=forks, become=become, become_method='sudo',
                                        check=False, diff=False)

        self.play = self._create_play(module_name, module_args, run_hosts)

    @classmethod
    def _create_play(cls, module_name, module_args, hosts):
        # create data structure that represents our play, including tasks, this is basically what our YAML loader does internally.
        play_source = dict(
                name="Ansible Play",
                hosts=hosts,
                gather_facts='no',
                tasks=[
                    dict(action=dict(module=module_name, args=module_args)),
                 ]
            )

        # Create play object, playbook objects use .load instead of init or new methods,
        # this will also automatically create the task objects from the info provided in play_source
        play = Play().load(play_source, variable_manager=variable_manager, loader=loader)
        return play

    def run(self):
        # Run it - instantiate task queue manager, which takes care of forking and setting up all objects to iterate over host list and tasks
        tqm = None
        try:
            tqm = TaskQueueManager(
                      inventory=inventory,
                      variable_manager=variable_manager,
                      loader=loader,
                      passwords=dict(),
                      stdout_callback=self.callback,  # Use our custom callback instead of the ``default`` callback plugin, which prints to stdout
                  )
            # most interesting data for a play is actually sent to the callback's methods
            result = tqm.run(self.play)  # NOQA
        except Exception:
            raise
        finally:
            # we always need to cleanup child procs and the structures we use to communicate with them
            if tqm is not None:
                tqm.cleanup()

            # Remove ansible tmpdir
            shutil.rmtree(C.DEFAULT_LOCAL_TMP, True)
        return self.callback.results
