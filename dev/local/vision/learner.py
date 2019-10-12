#AUTOGENERATED! DO NOT EDIT! File to edit: dev/21_vision_learner.ipynb (unless otherwise specified).

__all__ = ['has_pool_type', 'create_body', 'create_head', 'create_cnn_model', 'cnn_config', 'model_meta', 'cnn_learner',
           'unet_config', 'unet_learner']

#Cell
from ..test import *
from ..data.all import *
from ..optimizer import *
from ..learner import *
from ..metrics import *
from ..callback.all import *
from .core import *
from .augment import *
from . import models

#Cell
def _is_pool_type(l): return re.search(r'Pool[123]d$', l.__class__.__name__)

#Cell
def has_pool_type(m):
    "Return `True` if `m` is a pooling layer or has one in its children"
    if _is_pool_type(m): return True
    for l in m.children():
        if has_pool_type(l): return True
    return False

#Cell
def create_body(arch, pretrained=True, cut=None):
    "Cut off the body of a typically pretrained `arch` as determined by `cut`"
    model = arch(pretrained)
    #cut = ifnone(cut, cnn_config(arch)['cut'])
    if cut is None:
        ll = list(enumerate(model.children()))
        cut = next(i for i,o in reversed(ll) if has_pool_type(o))
    if   isinstance(cut, int):      return nn.Sequential(*list(model.children())[:cut])
    elif callable(cut): return cut(model)
    else:                           raise NamedError("cut must be either integer or a function")

#Cell
def create_head(nf, nc, lin_ftrs=None, ps=0.5, concat_pool=True, bn_final=False):
    "Model head that takes `nf` features, runs through `lin_ftrs`, and out `nc` classes."
    lin_ftrs = [nf, 512, nc] if lin_ftrs is None else [nf] + lin_ftrs + [nc]
    ps = L(ps)
    if len(ps) == 1: ps = [ps[0]/2] * (len(lin_ftrs)-2) + ps
    actns = [nn.ReLU(inplace=True)] * (len(lin_ftrs)-2) + [None]
    pool = AdaptiveConcatPool2d() if concat_pool else nn.AdaptiveAvgPool2d(1)
    layers = [pool, Flatten()]
    for ni,no,p,actn in zip(lin_ftrs[:-1], lin_ftrs[1:], ps, actns):
        layers += BnDropLin(ni, no, True, p, actn)
    if bn_final: layers.append(nn.BatchNorm1d(lin_ftrs[-1], momentum=0.01))
    return nn.Sequential(*layers)

#Cell
def create_cnn_model(arch, nc, cut, pretrained, lin_ftrs=None, ps=0.5, custom_head=None,
                     bn_final=False, concat_pool=True, init=nn.init.kaiming_normal_):
    "Create custom convnet architecture using `base_arch`"
    body = create_body(arch, pretrained, cut)
    if custom_head is None:
        nf = num_features_model(nn.Sequential(*body.children())) * (2 if concat_pool else 1)
        head = create_head(nf, nc, lin_ftrs, ps=ps, concat_pool=concat_pool, bn_final=bn_final)
    else: head = custom_head
    model = nn.Sequential(body, head)
    if init is not None: apply_init(model[1], init)
    return model

#Cell
@delegates(create_cnn_model)
def cnn_config(**kwargs):
    "Convenienc function to easily create a config for `create_cnn_model`"
    return kwargs

#Cell
def _default_split(m:nn.Module): return L(m[0], m[1:]).map(params)
def _resnet_split(m): return L(m[0][:6], m[0][6:], m[1:]).map(params)
def _squeezenet_split(m:nn.Module): return L(m[0][0][:5], m[0][0][5:], m[1:]).map(params)
def _densenet_split(m:nn.Module): return L(m[0][0][:7],m[0][0][7:], m[1:]).map(params)
def _vgg_split(m:nn.Module): return L(m[0][0][:22], m[0][0][22:], m[1:]).map(params)
def _alexnet_split(m:nn.Module): return L(m[0][0][:6], m[0][0][6:], m[1:]).map(params)

_default_meta    = {'cut':None, 'split':_default_split}
_resnet_meta     = {'cut':-2, 'split':_resnet_split }
_squeezenet_meta = {'cut':-1, 'split': _squeezenet_split}
_densenet_meta   = {'cut':-1, 'split':_densenet_split}
_vgg_meta        = {'cut':-2, 'split':_vgg_split}
_alexnet_meta    = {'cut':-2, 'split':_alexnet_split}

#Cell
model_meta = {
    models.resnet18 :{**_resnet_meta}, models.resnet34: {**_resnet_meta},
    models.resnet50 :{**_resnet_meta}, models.resnet101:{**_resnet_meta},
    models.resnet152:{**_resnet_meta},

    models.squeezenet1_0:{**_squeezenet_meta},
    models.squeezenet1_1:{**_squeezenet_meta},

    models.densenet121:{**_densenet_meta}, models.densenet169:{**_densenet_meta},
    models.densenet201:{**_densenet_meta}, models.densenet161:{**_densenet_meta},
    models.vgg11_bn:{**_vgg_meta}, models.vgg13_bn:{**_vgg_meta}, models.vgg16_bn:{**_vgg_meta}, models.vgg19_bn:{**_vgg_meta},
    models.alexnet:{**_alexnet_meta}}

#Cell
@delegates(Learner.__init__)
def cnn_learner(dbunch, arch, loss_func=None, pretrained=True, cut=None, splitter=None, config=None, **kwargs):
    "Build a convnet style learner"
    if config is None: config = {}
    meta = model_meta.get(arch, _default_meta)
    model = create_cnn_model(arch, get_c(dbunch), ifnone(cut, meta['cut']), pretrained, **config)
    learn = Learner(dbunch, model, loss_func=loss_func, splitter=ifnone(splitter, meta['split']), **kwargs)
    if pretrained: learn.freeze()
    return learn

#Cell
@delegates(models.unet.DynamicUnet.__init__)
def unet_config(**kwargs):
    "Convenience function to easily create a config for `DynamicUnet`"
    return kwargs

#Cell
@delegates(Learner.__init__)
def unet_learner(dbunch, arch, loss_func=None, pretrained=True, cut=None, splitter=None, config=None, **kwargs):
    "Build a unet learner from `dbunch` and `arch`"
    if config is None: config = {}
    meta = model_meta.get(arch, _default_meta)
    body = create_body(arch, pretrained, ifnone(cut, meta['cut']))
    try:    size = dbunch.train_ds[0][0].size
    except: size = dbunch.one_batch()[0].shape[-2:]
    model = models.unet.DynamicUnet(body, get_c(dbunch), size, **config)
    learn = Learner(dbunch, model, loss_func=loss_func, splitter=ifnone(splitter, meta['split']), **kwargs)
    if pretrained: learn.freeze()
    return learn
