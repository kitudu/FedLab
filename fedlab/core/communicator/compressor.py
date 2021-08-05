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

from abc import ABC, abstractmethod
import math
import torch

class Compressor(ABC):
    def __init__(self) -> None:
        super().__init__()

    @abstractmethod
    def initialize(self, named_parameters):
        raise NotImplementedError()

    @abstractmethod
    def compress(self):
        raise NotImplementedError()

    @abstractmethod
    def decompress(self):
        raise NotImplementedError()


class TopkCompressor(Compressor):
    """ Compressor for federated communication

        Top-k gradient or weights selection

        Args:
            compress_ratio (float): compress ratio
            fp16_values (bool): data type
            int32_indices (bool): data type
    """
    def __init__(self, compress_ratio, fp16_values=False, int32_indices=False):

        self.fp16_values = fp16_values
        self.int32_indices = int32_indices

        self.compress_ratio = compress_ratio if compress_ratio <= 1.0 else 1.0 / compress_ratio

        self.attributes = {}  # 定义压缩矩阵的基本信息： [numel, shape, top_k_samples]

    def initialize(self, named_parameters):
        for name, param in named_parameters:
            if torch.is_tensor(param):
                numel = param.numel()
                shape = param.shape
            else:
                raise ValueError("invalid type")

            top_k_samples = int(math.ceil(numel * self.compress_ratio))
            self.attributes[name] = (numel, shape, top_k_samples)

    def compress(self, tensor, name):
        if self.compress_ratio < 1.0 and name in self.attributes:

            tensor = tensor.view(-1)
            importance = tensor.abs()

            numel, shape, top_k_samples = self.attributes[name]

            _, indices = torch.topk(importance,
                                    top_k_samples,
                                    0,
                                    largest=True,
                                    sorted=False)
            values = tensor[indices]
            return (values, indices), (name, shape)
        else:
            raise ValueError("invalid value")

    def decompress(self, tensor, ctx):
        name, shape = ctx
        if self.compress_ratio < 1.0 and name in self.attributes:

            values, indices = tensor
            de_tensor = torch.zeros(size=shape).view(-1)
            de_tensor = de_tensor.index_put_([indices],
                                             values,
                                             accumulate=True).view(shape)
            return de_tensor
        else:
            raise ValueError("invalid value")


