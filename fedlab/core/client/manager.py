# Copyright 2021 Peng Cheng Laboratory (http://www.szpclab.com/) and FedLab Authors (smilelab.group)

# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at

#     http://www.apache.org/licenses/LICENSE-2.0

# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import logging
import torch

from ...utils.message_code import MessageCode

from ..communicator.processor import Package, PackageProcessor
from ..network_manager import NetworkManager


class ClientManager(NetworkManager):
    """Client Manager accept a object of DistNetwork and a ClientTrainer

    Args:
        network (DistNetwork): network configuration.
        trainer (ClientTrainer): performe local client training process.
    """
    def __init__(self, network, trainer):
        super().__init__(network)
        self._trainer = trainer

    def setup(self):
        """Setup agreements. Client report local client num."""
        super().setup()
        content = torch.Tensor([self._trainer.client_num]).int()
        setup_pack = Package(message_code=MessageCode.SetUp,
                             content=content,
                             data_type=1)
        PackageProcessor.send_package(setup_pack, dst=0)


class ClientPassiveManager(ClientManager):
    """Passive communication :class:`NetworkManager` for client in synchronous FL

    Args:
        network (DistNetwork): Distributed network to use.
        trainer (ClientTrainer): Subclass of :class:`ClientTrainer`. Provides :meth:`train` and :attr:`model`.
        logger (Logger, optional): object of :class:`Logger`.
    """
    def __init__(self, network, trainer, logger=None):
        super().__init__(network, trainer)

        if logger is None:
            logging.getLogger().setLevel(logging.INFO)
            self._LOGGER = logging
        else:
            self._LOGGER = logger

    def run(self):
        
        self._LOGGER.info("connecting with server")
        self.setup()
        self.main_loop()
        self._network.close_network_connection()

    def main_loop(self):
        """Actions to perform when receiving new message, including local training

        Main procedure of each client:
            1. client waits for data from server （PASSIVELY）
            2. after receiving data, client trains local model.
            3. client synchronizes with server actively.

        Note:
            Customize the control flow of client corresponding with :class:`MessageCode`.
        """
        while True:
            sender_rank, message_code, payload = PackageProcessor.recv_package(src=0)
            if message_code == MessageCode.Exit:
                break
            elif message_code == MessageCode.ParameterUpdate:
                model_parameters = payload[0]
                self._trainer.train(model_parameters=model_parameters)
                self.synchronize()
            else:
                raise ValueError("Invalid MessageCode {}. Please see MessageCode Enum".format(message_code))
        
    def synchronize(self):
        """Synchronize local model with server actively

        Note:
            communication agreements related:
            Overwrite this function to customize package for synchronizing.
        """
        self._LOGGER.info("synchronize model parameters with server")
        model_parameters = self._trainer.model_parameters
        pack = Package(message_code=MessageCode.ParameterUpdate,
                       content=model_parameters)
        PackageProcessor.send_package(pack, dst=0)


class ClientActiveManager(ClientManager):
    """Active communication :class:`NetworkManager` for client in asynchronous FL

    Args:
        network (DistNetwork): Distributed network to use.
        handler (ClientTrainer): Subclass of ClientTrainer. Provides :meth:`train` and :attr:`model`.
        logger (Logger, optional): object of :class:`Logger`.
    """
    def __init__(self, network, trainer, logger=None):
        super().__init__(network, trainer)

        if logger is None:
            logging.getLogger().setLevel(logging.INFO)
            self._LOGGER = logging
        else:
            self._LOGGER = logger

        self.model_time = None

    def main_loop(self):
        """Actions to perform on receiving new message, including local training

            1. client requests data from server (ACTIVE)
            2. after receiving data, client will train local model
            3. client will synchronize with server actively
        """
        while True:
            # request model actively
            self._LOGGER.info("request parameter procedure")
            pack = Package(message_code=MessageCode.ParameterRequest)
            PackageProcessor.send_package(pack, dst=0)
            
            # waits for data from
            sender_rank, message_code, payload = PackageProcessor.recv_package(
                src=0)
            
            if message_code == MessageCode.Exit:
                self._LOGGER.info(
                    "Recv {}, Process exiting".format(message_code))
                break
            elif message_code == MessageCode.ParameterUpdate:
                self._LOGGER.info("Package received from {}, message code {}".format(
                    sender_rank, message_code))
                model_parameters, self.model_time = payload[0], payload[1]
                # move loading model params to the start of training
                self._trainer.train(model_parameters=model_parameters)
                self.synchronize()
            else:
                raise ValueError("Invalid MessageCode {}. Please see MessageCode Enum".format(message_code))
            
    def synchronize(self):
        """Synchronize local model with server actively"""
        self._LOGGER.info("synchronize procedure")
        model_parameters = self._trainer.model_parameters
        pack = Package(message_code=MessageCode.ParameterUpdate)
        pack.append_tensor_list([model_parameters, self.model_time + 1])
        PackageProcessor.send_package(pack, dst=0)

    def _request_parameter(self):
        """send ParameterRequest"""
        self._LOGGER.info("request parameter procedure")
        pack = Package(message_code=MessageCode.ParameterRequest)
        PackageProcessor.send_package(pack, dst=0)
