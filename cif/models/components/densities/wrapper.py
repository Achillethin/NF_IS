import torch
import torch.nn as nn

from .density import Density
from ..networks import LipschitzNetwork


class WrapperDensity(Density):
    def __init__(self, density):
        super().__init__()
        self.density = density

    def _elbo(self, x):
        return self.density.elbo(x)

    def _sample(self, num_samples):
        return self.density.sample(num_samples)

    def _fixed_sample(self, noise):
        return self.density.fixed_sample(noise=noise)


class DequantizationDensity(WrapperDensity):
    def _elbo(self, x):
        return super()._elbo(x.add_(torch.rand_like(x)))


class PassthroughBeforeEvalDensity(WrapperDensity):
    def __init__(self, density, x):
        super().__init__(density)

        # XXX: It is inefficient to store the data separately, but this will work for # the (non-image) datasets we consider
        self.register_buffer("x", x)

    # We need to do it like this, i.e. we can't just override self.eval(), since
    # nn.Module.eval() just calls train(train_mode=False), so it wouldn't be called
    # recursively by modules containing this one.
    # TODO: Could do with hooks
    def train(self, train_mode=True):
        if not train_mode:
            self.training = True
            with torch.no_grad():
                self.elbo(self.x)
        super().train(train_mode)


class UpdateLipschitzBeforeForwardDensity(WrapperDensity):
    def __init__(self, density):
        super().__init__(density)
        self.register_forward_pre_hook(self._update_lipschitz)

    def _update_lipschitz(self, *args, **kwargs):
        for m in self.density.modules():
            if isinstance(m, LipschitzNetwork):
                m.update_lipschitz_constant()


class DataParallelDensity(nn.DataParallel):
    def elbo(self, x):
        return self("elbo", x)

    def sample(self, num_samples):
        # Bypass DataParallel
        return self.module.sample(num_samples)

    def fixed_sample(self, noise=None):
        # Bypass DataParallel
        return self.module.fixed_sample(noise=noise)
