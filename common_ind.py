import math
import time

import numpy as np
import pylab as plt
from profilehooks import profile
import matplotlib.gridspec as gridspec

try:
    from collections import OrderedDict
except:
    from ordereddict import OrderedDict  #XD

class Delta(object):
    def __init__(self):
        self.prev_val = None
        
    def step(self, x):
        if self.prev_val == None:
            self.prev_val = x
            return 0
        delta = x - self.prev_val
        self.prev_val = x
        return delta
    
    def reset(self):
        self.prev_val = None

class SMA(object):
    def __init__(self, n):
        self.__dict__.update(locals())
        del self.self
        self.reset()
           
    def step(self, x):
        if self.n == 1:
            return x
        
        if self.hist_len == self.n:
            first = self.history.pop(0)
            self.hist_sum -= first
            self.hist_len -= 1
            
        self.history.append(x)
        self.hist_sum += x
        self.hist_len += 1
        
        ma = self.hist_sum * 1. / self.hist_len
        return ma
    
    def reset(self):
        self.history = []
        self.hist_sum = 0.
        self.hist_len = 0
        
class EMA(object):
    def __init__(self, n):
        self.__dict__.update(locals())
        del self.self
        self.alpha = 2./(self.n + 1.)
        self.reset()
           
    def reset(self):
        self.sum = 0.
        self.sum_cnt = 0
        
    def step(self, x):
        if self.n == 1:
            return x
    
        if self.sum_cnt < self.n:
            self.sum += x
            self.sum_cnt += 1
            self.ema = self.sum * 1. / self.sum_cnt
        else:
            self.ema = self.ema * (1. - self.alpha) + x * self.alpha
        return self.ema

class MVAR2(object):
    def __init__(self, n):
        self.n = n
        
#    @profile
    def step(self, x_arr):
        n = min(x_arr.size, self.n)
        ma = x_arr[-n:].mean()
#        var = (x_arr[-n:]**2).mean() - ma**2
        var = np.var(x_arr[-n:])
        return ma, var
        
class MVAR(object):
    def __init__(self, n):
        self.n = n
        self.sum = 0.
        self.sum2 = 0.
        self.init_full_summed = False 
        
#    @profile
    def step(self, x_arr):
        if not self.init_full_summed:
            n = min(x_arr.size, self.n)
            ma = x_arr[-n:].mean()
            var = np.var(x_arr[-n:])
            self.init_full_summed = True
            return ma, var
        
        self.sum += x_arr[-1]
        self.sum2 += x_arr[-1]**2
        if x_arr.size <= self.n:
            n = x_arr.size
        else:
            self.sum -= x_arr[-1-self.n]
            self.sum2 -= x_arr[-1-self.n]**2
            n = self.n
        ma = self.sum / n
        var = self.sum2 / n - ma**2
        return ma, var
    
class MDEV(object):
    def __init__(self, n, dev_type='standard', warmup_steps=None, filter_thld=np.inf):
        self.__dict__.update(locals())
        del self.self
        assert self.dev_type in ['standard', 'absolute'], self.dev_type
        if self.warmup_steps is None:
            self.warmup_steps = self.n / 10
        self.dev_EMA = EMA(n)
        self.steps = 0
        self.filtered_steps = 0
        
        if self.dev_type == 'standard' and not np.isinf(self.filter_thld):
            self.filter_thld = self.filter_thld ** 2
        
    def step(self, x):
        dev = x**2 if self.dev_type == 'standard' else abs(x)
#        if self.filter_thld is not None and self.dev_EMA.sum_cnt >= self.warmup_steps:
        if self.dev_EMA.sum_cnt >= self.warmup_steps:
            if dev > self.dev_EMA.ema * self.filter_thld:
                self.filtered_steps += 1
#                print self.filtered_steps, '/', self.steps, '=', self.filtered_steps * 1. / self.steps, \
#                    ':', dev, '>', self.dev_EMA.ema, '*', self.filter_thld, \
#                    '( =', self.dev_EMA.ema * self.filter_thld, ')'
            dev = min(dev, self.dev_EMA.ema * self.filter_thld)
        mdev = self.dev_EMA.step(dev)
        if self.dev_type == 'standard':
            mdev = np.sqrt(mdev) 
        self.steps += 1
        
        if self.dev_EMA.sum_cnt >= self.warmup_steps:
            return mdev
        else:
            return None

def clip_mod(max_mod, x):
    if abs(x) < max_mod:
        return x
    return max_mod if x > 0 else -max_mod

class Indicator(object):
    def __init__(self):
        return
#    def standardize(self):
#        y_stdev = self.y_MDEV.step(self.y)
#        self.y = self.y / y_stdev if y_stdev is not None else 0.
#        
#        if hasattr(self, 'y_ma'): # for dMACD
#            y_ma_stdev = self.y_ma_MDEV.step(self.y_ma)
#            self.y_ma = self.y_ma / y_ma_stdev if y_ma_stdev is not None else 0.
   
    def postprocess(self):
        y = self.y
        if self.standardized:
            y_stdev = self.y_MDEV.step(self.y)
            if y_stdev is not None:
                assert y_stdev != 0
                y_std = clip_mod(self.filter_thld, self.y / y_stdev)
                y = y_std * y_stdev 
            else:
                y_std = 0.
            self.y = y_std
        if hasattr(self, 'y_MA'): # for dMACD
            y_ma = self.y_MA.step(y)
            if self.standardized:
                y_ma_stdev = self.y_ma_MDEV.step(y_ma)
                if y_ma_stdev is not None:
                    assert y_ma_stdev != 0
                    self.y_ma = clip_mod(self.filter_thld, y_ma / y_ma_stdev)
                else:
                    self.y_ma = 0.
            else:
                self.y_ma = y_ma
   
    def output(self):
        rval = OrderedDict()
        rval[self.name] = self.y
        if hasattr(self, 'y_ma'):
            rval[self.name + '.ma'] = self.y_ma
        return rval
        
class IndicatorOld(object):
    def __init__(self):
        return
    
    def standardize(self):
        if not hasattr(self, 'y_MVAR'):
            self.mvar_win = int(self.mvar_days * self.s.hours_per_day * 60 * 60 * 2)
            self.y_MVAR = MVAR(self.mvar_win)
            self.std_y = np.zeros(self.buffer_len)
            self.y_ma = np.zeros(self.buffer_len)
            self.y_mvar = np.zeros(self.buffer_len)
            self.buffers += [self.std_y, self.y_ma, self.y_mvar]
            
            if hasattr(self, 'y_ema'): # for dMACD
                self.std_y_ema = np.zeros(self.buffer_len)
                self.buffers += [self.std_y_ema]
        y_ma, y_mvar = self.y_MVAR.step(self.y[:self.s.now])
        std_y = (self.y[self.s.now - 1] - y_ma) / np.sqrt(y_mvar + 1e-16)
        if self.s.now < self.mvar_win / 4:
            y_ma, y_mvar, std_y = 0., 0., 0.
        self.y_ma[self.s.now - 1], self.y_mvar[self.s.now - 1], self.std_y[self.s.now - 1] = y_ma, y_mvar, std_y
        
        if hasattr(self, 'y_ema'): # for dMACD
            std_y_ema = (self.y_ema[self.s.now - 1] - y_ma) / np.sqrt(y_mvar + 1e-16)
            self.std_y_ema[self.s.now - 1] = std_y_ema

    def output(self):
        if self.standardized:
            v = self.std_y[self.s.now - 1]
        else:
            v = self.y[self.s.now - 1]
        return {self.name : v}
    
class DeltaPattern():
    def __init__(self, s, n, m, input_key='last_price', name=None, escape_opening=1, mvar_days=1, standardized=True):
        self.__dict__.update(locals())
        del self.self
        self.name = 'DeltaPattern(' + str(self.m) + ')'
        self.x = self.s.history[self.input_key]
        self.dx = np.zeros(self.buffer_len) 
        
    def step(self):
        if self.s.history['time_in_ticks'][self.s.now - 1] < self.escape_opening:
            dx = 0.
        else:
            dx = self.x[self.s.now - 1] - self.x[self.s.now - 2]
        self.dx[self.s.now - 1] = dx
        
    def output(self):
        if self.s.now < self.n * self.m:
            dxes = np.zeros(self.m)
        else:
            dxes = self.dx[self.s.now - self.n * self.m : self.s.now].reshape(self.m, self.n).sum(axis=1)
        
        rval = OrderedDict()
        for i in range(self.m):
            rval[self.name + '[' + str(i) + ']'] = dxes[i]
        return rval
        
class MACD(Indicator):
    def __init__(self, s, n, m, input_key='last_price',
                 name=None, escape_opening=1, standardized=False, filter_thld=np.inf
                 ):
        self.__dict__.update(locals())
        del self.self
        
#        self.buffer_len = self.s.buffer_len
        if self.name is None:
            self.name = 'macd' + str(int(m / 120)) + 'm'
        
        self.x = self.s.history[self.input_key]
#        self.fast = np.zeros(self.buffer_len)
#        self.slow = np.zeros(self.buffer_len)
#        self.y = np.zeros(self.buffer_len)
#        self.buffers = [self.fast, self.slow, self.y]
        
        self.fast_EMA = EMA(n)
        self.slow_EMA = EMA(m)
        self.y = 0.
#        super(MACD, self).__init__()
        if self.standardized:
            self.y_MDEV = MDEV(self.m*50, dev_type='standard', warmup_steps=self.m*5, filter_thld=self.filter_thld)
            
    def step(self):
        if self.s.history['time_in_ticks'][self.s.now - 1] < self.escape_opening:
            self.fast_EMA.reset()
            self.slow_EMA.reset()
        self.fast_ema = self.fast_EMA.step(self.x[self.s.now - 1])
        self.slow_ema = self.slow_EMA.step(self.x[self.s.now - 1])
        self.y = self.fast_ema - self.slow_ema
#        self.fast[self.s.now - 1], self.slow[self.s.now - 1], self.y[self.s.now - 1] = fast_ema, slow_ema, fast_ema - slow_ema
        
#        self.postprocess()
            
    def output(self):
        rval = OrderedDict()
        rval[self.name + '.fast'] = self.fast_ema
        rval[self.name + '.slow'] = self.slow_ema
        rval[self.name] = self.y
        return rval
        
class dMACD(Indicator):
    def __init__(self, s, n, m, k, input_key='last_price',
                 name=None, escape_opening=1, standardized=True, filter_thld=np.inf
                 ):
        self.__dict__.update(locals())
        del self.self
        
#        self.buffer_len = self.s.buffer_len
        if self.name is None:
            self.name = 'dmacd' + str(int(m / 120)) + 'm'
        
        self.x = self.s.history[self.input_key]
#        self.fast = np.zeros(self.buffer_len)
#        self.slow = np.zeros(self.buffer_len)
#        self.y = np.zeros(self.buffer_len)
#        self.y_ema = np.zeros(self.buffer_len)
#        self.buffers = [self.fast, self.slow, self.y, self.y_ema]
        
        self.fast_EMA = EMA(n)
        self.slow_EMA = EMA(m)
        self.y_MA = SMA(k)
#        self.y = 0.
#        self.y_ma = 0.
#        super(dMACD, self).__init__()
        if self.standardized:
            self.y_MDEV = MDEV(self.n*50, dev_type='standard', warmup_steps=self.n*5, filter_thld=self.filter_thld)
            self.y_ma_MDEV = MDEV(self.k*50, dev_type='standard', warmup_steps=self.k*5, filter_thld=self.filter_thld)
    
    def step(self):
        if self.s.now - 1 == 0 or self.s.history['time_in_ticks'][self.s.now - 1] < self.escape_opening:
            self.fast_EMA.reset()
            self.slow_EMA.reset()
            self.y_MA.reset()
            dx = 0.
        else:
            dx = self.x[self.s.now - 1] - self.x[self.s.now - 2]
        dx_fast_ema = self.fast_EMA.step(dx)
        dx_slow_ema = self.slow_EMA.step(dx)
        d = OrderedDict()
        self.y = dx_fast_ema - dx_slow_ema
        
        self.postprocess()
    
class ExpectedChange(Indicator):
    def __init__(self, s, n, input_key='last_price',
                 name=None, escape_opening=3*60*2, standardized=True, filter_thld=np.inf
                 ):
        self.__dict__.update(locals())
        del self.self
        
        if self.name is None:
            self.name = 'ec' + str(int(self.n / 120)) + 'm'
        
        self.x = self.s.history[self.input_key]
#        super(ExpectedChange, self).__init__()
        if self.standardized:
            self.y_MDEV = MDEV(self.n*50, dev_type='standard', warmup_steps=self.n*5, filter_thld=self.filter_thld)
            
    def step(self):
        if self.s.history['time_in_ticks'][self.s.now - 1] < self.escape_opening or \
            self.s.now + self.n - 1 > self.s.history['time_in_ticks'].shape[0] - 1 or \
            self.s.history['time_in_ticks'][self.s.now + self.n - 1] < self.s.history['time_in_ticks'][self.s.now - 1]:
            self.y = 0.
        else:
            self.y = self.x[self.s.now : self.s.now + self.n].mean() - self.x[self.s.now - 1]
            
        self.orig_y = self.y
        self.postprocess()
     
    def output(self):
        rval = OrderedDict()
        rval[self.name] = self.y
        rval[self.name + '.orig'] = self.orig_y
        return rval
    
class TimeInfo():
    def __init__(self, s, input_key='time_in_ticks',
                 name=None
                 ):
        self.__dict__.update(locals())
        del self.self
        
        if self.name is None:
            self.name = ''
        
        self.x = self.s.history[self.input_key]
        self.day_idx = -1
        self.ticks_per_day = self.s.hours_per_day * 60 * 60 * 2
        
    def step(self):
        if self.x[self.s.now - 1] == 0:
            self.day_idx += 1
            
    def output(self):
        rval = OrderedDict()
        rval[self.name + 'day'] = self.day_idx
        rval[self.name + 'time'] = self.x[self.s.now - 1] #* 1. / self.ticks_per_day
        return rval
               
class ddMACD(Indicator):
    def __init__(self, s, n, m,
                 name=None, escape_opening=1, mvar_days=None, standardized=True
                 ):
        self.__dict__.update(locals())
        del self.self
        
        self.buffer_len = self.s.buffer_len
        if self.name is None:
            self.name = 'ACC(' + str(int(n / 120)) + 'm)'
        
        self.x = self.s.history['last_price']
        self.ddx = np.zeros(self.buffer_len)
        self.fast = np.zeros(self.buffer_len)
        self.slow = np.zeros(self.buffer_len)
        self.y = np.zeros(self.buffer_len)
        self.buffers = [self.ddx, self.fast, self.slow, self.y]
            
        self.fast_EMA = EMA(n)
        self.slow_EMA = EMA(m)
        self.dx_Delta = Delta()
        
    def step(self):
        if self.s.history['time_in_ticks'][self.s.now - 1] < self.escape_opening:  # Avoid big jumps near opening. Notice that dMACD and MACD do not have this issue. 
            self.fast_EMA.reset()
            self.slow_EMA.reset()
            self.dx_Delta.reset()
            dx = 0
        else:
            dx = self.x[self.s.now - 1] - self.x[self.s.now - 2]
        ddx = self.dx_Delta.step(dx)
        ddx_fast_ema = self.fast_EMA.step(ddx)
        ddx_slow_ema = self.slow_EMA.step(ddx)
        self.ddx[self.s.now - 1] = ddx
        self.y[self.s.now - 1] = ddx_fast_ema - ddx_slow_ema
        if self.standardized:
            self.standardize()
             
class ACC(Indicator):
    def __init__(self, s, n,
                 name=None, escape_opening=1, mvar_days=None, standardized=True
                 ):
        self.__dict__.update(locals())
        del self.self
        
        self.buffer_len = self.s.buffer_len
        if self.name is None:
            self.name = 'ACC(' + str(int(n / 120)) + 'm)'
        
        self.x = self.s.history['last_price']
        self.ddx = np.zeros(self.buffer_len)
        self.y = np.zeros(self.buffer_len)
        self.buffers = [self.ddx, self.y]
        
        self.ddx_EMA = EMA(n)
        self.dx_Delta = Delta()
        
    def step(self):
#        if self.s.market_just_opened():
        if self.s.history['time_in_ticks'][self.s.now - 1] < self.escape_opening:  # Avoid big jumps near opening. Notice that dMACD and MACD do not have this issue. 
            self.ddx_EMA.reset()
            self.dx_Delta.reset()
            dx = 0
        else:
            dx = self.x[self.s.now - 1] - self.x[self.s.now - 2]
        ddx = self.dx_Delta.step(dx)
        acc = self.ddx_EMA.step(ddx)
        self.ddx[self.s.now - 1] = ddx
        self.y[self.s.now - 1] = acc
        if self.standardized:
            self.standardize()
    
from build_tick_dataset import load_ticks
from strategy import Strategy
  
def compare(a, b):
    print 'diff.mean =', np.abs((a - b)).mean(), 'diff.max =', np.abs((a - b)).max(), '/', np.abs(a).mean() 
        
def test_macd():
    ticks = load_ticks('dc', 'pp', 2015, range(9,10), use_cache=True)
    s = Strategy('pp09_macd', ticks, 3.75)
    
    inds = [MACD(s, 1*60*2, 5*60*2, standardized=False, escape_opening=1),
            MACD(s, 2*60*2, 10*60*2, standardized=False, escape_opening=1),
            MACD(s, 10*60*2, 60*60*2, standardized=False, escape_opening=0)
            ]
    
    for ind in inds:
        s.add_indicator(ind)
    
    s.run()
    
def test_all():
    ticks = load_ticks('dc', 'pp', 2015, range(6,10), use_cache=True)
    s = Strategy('pp1506-1509_common_stride10', ticks, 3.75)
    
    inds = [
            MACD(s, 1*60*2, 5*60*2, escape_opening=1),
            MACD(s, 2*60*2, 10*60*2, escape_opening=1),
            MACD(s, 10*60*2, 60*60*2, escape_opening=0),
            dMACD(s, 1*60*2, 5*60*2, 2.5*60*2, standardized=True, escape_opening=1),
            dMACD(s, 2*60*2, 10*60*2, 2.5*60*2, standardized=True, escape_opening=1),
            dMACD(s, 10*60*2, 60*60*2, 30*60*2, standardized=True, escape_opening=0, filter_thld=3.),
            ExpectedChange(s, 5*60*2, standardized=True, escape_opening=3*60*2),
            ExpectedChange(s, 10*60*2, standardized=True, escape_opening=3*60*2),
            TimeInfo(s)
            ]
    
    for ind in inds:
        s.add_indicator(ind)
    
    s.run()
  
if __name__ == '__main__':
    test_all()