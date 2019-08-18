#AUTOGENERATED! DO NOT EDIT! File to edit: dev/05_data_core.ipynb (unless otherwise specified).

__all__ = ['get_files', 'FileGetter', 'image_extensions', 'get_image_files', 'ImageGetter', 'RandomSplitter',
           'GrandparentSplitter', 'parent_label', 'RegexLabeller', 'Category', 'Categorize', 'MultiCategory',
           'MultiCategorize', 'one_hot_decode', 'OneHotEncode', 'ToTensor', 'TfmdDL', 'Cuda', 'ByteToFloatTensor',
           'Normalize', 'broadcast_vec', 'DataBunch']

from ..imports import *
from ..test import *
from ..core import *
from .load import *
from .transform import *
from .pipeline import *
from .external import *
from ..notebook.showdoc import show_doc

def _get_files(p, fs, extensions=None):
    p = Path(p)
    res = [p/f for f in fs if not f.startswith('.')
           and ((not extensions) or f'.{f.split(".")[-1].lower()}' in extensions)]
    return res

def get_files(path, extensions=None, recurse=True, include=None):
    "Get all the files in `path` with optional `extensions`, optionally with `recurse`."
    path = Path(path)
    extensions = setify(extensions)
    extensions = {e.lower() for e in extensions}
    if recurse:
        res = []
        for i,(p,d,f) in enumerate(os.walk(path)): # returns (dirpath, dirnames, filenames)
            if include is not None and i==0: d[:] = [o for o in d if o in include]
            else:                            d[:] = [o for o in d if not o.startswith('.')]
            res += _get_files(p, f, extensions)
    else:
        f = [o.name for o in os.scandir(path) if o.is_file()]
        res = _get_files(path, f, extensions)
    return L(res)

def FileGetter(suf='', extensions=None, recurse=True, include=None):
    "Create `get_files` partial function that searches path suffix `suf` and passes along args"
    def _inner(o, extensions=extensions, recurse=recurse, include=include): return get_files(o/suf, extensions, recurse, include)
    return _inner

image_extensions = set(k for k,v in mimetypes.types_map.items() if v.startswith('image/'))

def get_image_files(path, recurse=True, include=None):
    "Get image files in `path` recursively."
    return get_files(path, extensions=image_extensions, recurse=recurse, include=include)

def ImageGetter(suf='', recurse=True, include=None):
    "Create `get_image_files` partial function that searches path suffix `suf` and passes along `kwargs`"
    def _inner(o, recurse=recurse, include=include): return get_image_files(o/suf, recurse, include)
    return _inner

def RandomSplitter(valid_pct=0.2, seed=None, **kwargs):
    "Create function that splits `items` between train/val with `valid_pct` randomly."
    def _inner(o, **kwargs):
        if seed is not None: torch.manual_seed(seed)
        rand_idx = L(int(i) for i in torch.randperm(len(o)))
        cut = int(valid_pct * len(o))
        return rand_idx[cut:],rand_idx[:cut]
    return _inner

def _grandparent_idxs(items, name): return mask2idxs(Path(o).parent.parent.name == name for o in items)

def GrandparentSplitter(train_name='train', valid_name='valid'):
    "Split `items` from the grand parent folder names (`train_name` and `valid_name`)."
    def _inner(o, **kwargs):
        return _grandparent_idxs(o, train_name),_grandparent_idxs(o, valid_name)
    return _inner

def parent_label(o, **kwargs):
    "Label `item` with the parent folder name."
    return o.parent.name if isinstance(o, Path) else o.split(os.path.sep)[-1]

def RegexLabeller(pat):
    "Label `item` with regex `pat`."
    pat = re.compile(pat)
    def _inner(o, **kwargs):
        res = pat.search(str(o))
        assert res,f'Failed to find "{pat}" in "{o}"'
        return res.group(1)
    return _inner

class Category(str, ShowTitle): _show_args = {'label': 'category'}

class Categorize(ItemTransform):
    "Reversible transform of category string to `vocab` id"
    order=1
    def __init__(self, vocab=None):
        self.vocab = vocab
        self.o2i = None if vocab is None else {v:k for k,v in enumerate(vocab)}

    def setup(self, dsrc):
        if not dsrc: return
        if self.vocab is None:
            dsrc = getattr(dsrc,'train',dsrc)
            self.vocab,self.o2i = uniqueify(dsrc, sort=True, bidir=True)

    def encodes(self, o): return self.o2i[o]
    def decodes(self, o)->Category: return self.vocab[o]

Category.create = Categorize

class MultiCategory(L):
    def show(self, ctx=None, sep=';', **kwargs): return show_title(sep.join(self.mapped(str)), ctx=ctx)

class MultiCategorize(Categorize):
    "Reversible transform of multi-category strings to `vocab` id"
    def setup(self, dsrc):
        if not dsrc: return
        if self.vocab is None:
            dsrc1 = getattr(dsrc,'train',dsrc)
            vals = set()
            for b in dsrc1: vals = vals.union(set(b))
            self.vocab,self.o2i = uniqueify(list(vals), sort=True, bidir=True)
        setattr(dsrc, 'vocab', self.vocab)

    def encodes(self, o):                return [self.o2i  [o_] for o_ in o]
    def decodes(self, o)->MultiCategory: return [self.vocab[o_] for o_ in o]

MultiCategory.create = MultiCategorize

def one_hot_decode(x, vocab=None):
    return L(vocab[i] if vocab else i for i,x_ in enumerate(x) if x_==1)

class OneHotEncode(Transform):
    "One-hot encodes targets and optionally decodes with `vocab`"
    order=2
    def __init__(self, do_encode=True, vocab=None): self.do_encode,self.vocab = do_encode,vocab

    def setup(self, dsrc):
        if self.vocab is not None:  self.c = len(self.vocab)
        else: self.c = len(L(getattr(dsrc, 'vocab', None)))
        if not self.c: warn("Couldn't infer the number of classes, please pass a `vocab` at init")

    def encodes(self, o)->Tensor: return one_hot(o, self.c) if self.do_encode else tensor(o).byte()
    def decodes(self, o)->L: return one_hot_decode(o, self.vocab)

class ToTensor(Transform):
    "Convert item to appropriate tensor class"
    order = 15

_dl_tfms = ('after_item','before_batch','after_batch')

@delegates()
class TfmdDL(DataLoader):
    "Transformed `DataLoader`"
    def __init__(self, dataset, bs=16, shuffle=False, **kwargs):
        for nm in _dl_tfms:
            kwargs[nm] = Pipeline(kwargs.get(nm,None), as_item=(nm=='before_batch'))
            kwargs[nm].setup(self)
        super().__init__(dataset, bs=bs, shuffle=shuffle, **kwargs)
        it  = self.do_item(0)
        its = self.do_batch([it])
        #TODO do we still need?
        self._retain_ds = partial(retain_types, typs=L(it ).mapped(type))
        self._retain_dl = partial(retain_types, typs=L(its).mapped(type))

    def before_iter(self):
        super().before_iter()
        filt = getattr(self.dataset, 'filt', None)
        for nm in _dl_tfms:
            f = getattr(self,nm)
            if isinstance(f,Pipeline): f.filt=filt

    def decode(self, b): return self.before_batch.decode(self.after_batch.decode(self._retain_dl(b)))
    def decode_batch(self, b, max_samples=10, ds_decode=True): return self._decode_batch(self.decode(b), max_samples, ds_decode)

    def _decode_batch(self, b, max_samples=10, ds_decode=True):
        f = compose(self._retain_ds, self.after_item.decode)
        if ds_decode: f = compose(f, getattr(self.dataset,'decode',noop))
        return L(batch_to_samples(b, max_samples=max_samples)).mapped(f)

    def show_batch(self, b=None, max_samples=10, ctxs=None, **kwargs):
        "Show `b` (defaults to `one_batch`), a list of lists of pipeline outputs (i.e. output of a `DataLoader`)"
        if b is None: b = self.one_batch()
        b = self.decode(b)
        if ctxs is None:
            if hasattr(b[0], 'get_ctxs'): ctxs = b[0].get_ctxs(max_samples=max_samples, **kwargs)
            else: ctxs = [None] * len(b[0] if is_iter(b[0]) else b)
        db = self._decode_batch(b, max_samples, False)
        ctxs = [self.dataset.show(o, ctx=ctx, **kwargs) for o,ctx in zip(db, ctxs)]
        if hasattr(b[0], 'display'): b[0].display(ctxs)

@docs
class Cuda(Transform):
    "Move batch to `device` (defaults to `defaults.device`)"
    def __init__(self,device=None):
        self.device=default_device() if device is None else device
        super().__init__(filt=None, as_item=False)
    def encodes(self, b): return to_device(b, self.device)
    def decodes(self, b): return to_cpu(b)

    _docs=dict(encodes="Move batch to `device`", decodes="Return batch to CPU")

class ByteToFloatTensor(Transform):
    "Transform image to float tensor, optionally dividing by 255 (e.g. for images)."
    order = 20 #Need to run after CUDA if on the GPU
    def __init__(self, div=True, div_mask=False, filt=None, as_item=True):
        super().__init__(filt=filt,as_item=as_item)
        self.div,self.div_mask = div,div_mask

    def encodes(self, o:TensorImage): return o.float().div_(255.) if self.div else o.float()
    def decodes(self, o:TensorImage): return o.clamp(0., 1.) if self.div else o
    def encodes(self, o:TensorMask)->TensorMask: return o.div_(255.).long() if self.div_mask else o.long()
    def decodes(self, o:TensorMask): return o

@docs
class Normalize(Transform):
    "Normalize/denorm batch of `TensorImage`"
    order=99
    def __init__(self, mean, std): self.mean,self.std = mean,std
    def encodes(self, x:TensorImage): return (x-self.mean) / self.std
    def decodes(self, x:TensorImage): return (x*self.std ) + self.mean

    _docs=dict(encodes="Normalize batch", decodes="Denormalize batch")

def broadcast_vec(dim, ndim, *t, cuda=True):
    "Make a vector broadcastable over `dim` (out of `ndim` total) by prepending and appending unit axes"
    v = [1]*ndim
    v[dim] = -1
    f = to_device if cuda else noop
    return [f(tensor(o).view(*v)) for o in t]

@docs
class DataBunch(GetAttr):
    "Basic wrapper around several `DataLoader`s."
    _xtra = 'one_batch show_batch dataset'.split()

    def __init__(self, *dls): self.dls,self.default = dls,dls[0]
    def __getitem__(self, i): return self.dls[i]

    train_dl,valid_dl = add_props(lambda i,x: x[i])
    train_ds,valid_ds = add_props(lambda i,x: x[i].dataset)

    _docs=dict(__getitem__="Retrieve `DataLoader` at `i` (`0` is training, `1` is validation)",
              train_dl="Training `DataLoader`",
              valid_dl="Validation `DataLoader`",
              train_ds="Training `Dataset`",
              valid_ds="Validation `Dataset`")