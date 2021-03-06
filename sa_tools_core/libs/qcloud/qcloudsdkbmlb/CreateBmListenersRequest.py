# -*- coding: utf-8 -*-

from ..qcloudsdkcore.request import Request

class CreateBmListenersRequest(Request):

    def __init__(self):
        super(CreateBmListenersRequest, self).__init__(
            'bmlb', 'qcloudcliV1', 'CreateBmListeners', 'bmlb.api.qcloud.com')

    def get_listeners(self):
        return self.get_params().get('listeners')

    def set_listeners(self, listeners):
        self.add_param('listeners', listeners)

    def get_loadBalancerId(self):
        return self.get_params().get('loadBalancerId')

    def set_loadBalancerId(self, loadBalancerId):
        self.add_param('loadBalancerId', loadBalancerId)
