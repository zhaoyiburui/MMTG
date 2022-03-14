'''
Author: Aman
Date: 2022-03-04 14:13:14
Contact: cq335955781@gmail.com
LastEditors: Aman
LastEditTime: 2022-03-04 14:13:50
'''


import datetime


def format_time(elapsed):
    '''
    Takes a time in seconds and returns a string hh:mm:ss
    '''
    # Round to the nearest second.
    elapsed_rounded = int(round((elapsed)))
    # Format as hh:mm:ss
    return str(datetime.timedelta(seconds=elapsed_rounded))