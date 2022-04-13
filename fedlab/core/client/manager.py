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

import torch

from ...utils import Logger
from ...utils.message_code import MessageCode
from ..network_manager import NetworkManager


class ClientManager(NetworkManager):
    """Base class for ClientManager.

    :class:`ClientManager` defines client activation for different communication stages.

    Args:
        network (DistNetwork): Network configuration.
        trainer (ClientTrainer): Subclass of :class:`ClientTrainer`. Provides :meth:`train` and :attr:`model`. Define local client training procedure.
    """

    def __init__(self, network, trainer):
        super().__init__(network)
        self._trainer = trainer

    def setup(self):
        """Initialization stage.

        :class:`ClientManager` reports number of clients simulated by current client process.
        """
        super().setup()
        tensor = torch.Tensor([self._trainer.client_num]).int()
        self._network.send(content=tensor,
                           message_code=MessageCode.SetUp,
                           dst=0)


class ClientPassiveManager(ClientManager):
    """Passive communication :class:`NetworkManager` for client in synchronous FL pattern.

    Args:
        network (DistNetwork): network configuration.
        trainer (ClientTrainer): Subclass of :class:`ClientTrainer`. Provides :meth:`train` and :attr:`model`. Define local client training procedure.
        logger (Logger): object of :class:`Logger`.
    """

    def __init__(self, network, trainer, logger=None):
        super().__init__(network, trainer)
        self._LOGGER = Logger() if logger is None else logger

    def main_loop(self):
        """Actions to perform when receiving a new message, including local training.

        Main procedure of each client:
            1. client waits for data from server (PASSIVELY).
            2. after receiving data, client start local model training procedure.
            3. client synchronizes with server actively.
        """
        while True:
            sender_rank, message_code, payload = self._network.recv(src=0)
            if message_code == MessageCode.Exit:
                break
            elif message_code == MessageCode.ParameterUpdate:
                self._trainer.local_process(payload)
                self.synchronize()
            else:
                raise ValueError(
                    "Invalid MessageCode {}. Please check MessageCode Enum".
                    format(message_code))

    def synchronize(self):
        """Synchronize with server"""
        self._LOGGER.info("Uploading information to server")
        self._network.send(content=self._trainer.uplink_package,
                           message_code=MessageCode.ParameterUpdate,
                           dst=0)


class ClientActiveManager(ClientManager):
    """Active communication :class:`NetworkManager` for client in asynchronous FL pattern.

    Args:
        network (DistNetwork): network configuration.
        trainer (ClientTrainer): Subclass of :class:`ClientTrainer`. Provides :meth:`train` and :attr:`model`. Define local client training procedure.
        logger (Logger, optional): object of :class:`Logger`.
    """

    def __init__(self, network, trainer, logger=None):
        super().__init__(network, trainer)
        self._LOGGER = Logger() if logger is None else logger

    def main_loop(self):
        """Actions to perform on receiving new message, including local training

            1. client requests data from server (ACTIVE)
            2. after receiving data, client will train local model
            3. client will synchronize with server actively
        """
        while True:
            # request model actively
            self._LOGGER.info("request parameter procedure")
            self._network.send(message_code=MessageCode.ParameterRequest,
                               dst=0)

            # waits for data from
            sender_rank, message_code, payload = self._network.recv(src=0)
            if message_code == MessageCode.Exit:
                self._LOGGER.info(
                    "Recv {}, process exiting.".format(message_code))
                break
            elif message_code == MessageCode.ParameterUpdate:
                self._trainer.local_process(payload)
                self.synchronize(self._trainer.uplink_package)
            else:
                raise ValueError(
                    "Invalid MessageCode {}. Please check MessageCode Enum".
                    format(message_code))

    def synchronize(self, uplink_content):
        """Synchronize with server"""
        self._LOGGER.info("Uploading information to server")
        self._network.send(content=uplink_content,
                           message_code=MessageCode.ParameterUpdate,
                           dst=0)
