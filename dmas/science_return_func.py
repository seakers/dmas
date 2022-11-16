import numpy as np
import math


def measperf(x,y,z,w):
    a = 8.94e-5
    b = 1.45e-3
    c = 0.164
    d = 1.03
    a1 = 1.97e-6
    b1 = -0.007
    a2 = -1.42e-6
    b2 = 3.08e-4
    c1 = 13.14
    c2 = -2.81e-2
    d2 = 1.03
    meas = a*x-b*y-c*np.log10(z)+d
    spatial = a1*pow(math.e,(b1*y+c1))
    temporal = a2*pow(w,3)+b2*pow(w,2)+c2*w+d2
    return 0.6*meas+0.2*spatial+0.2*temporal

if __name__ == '__main__':
    x = 1000
    y = 10
    z = 3.25
    w = 1
    print(measperf(x,y,z,w))