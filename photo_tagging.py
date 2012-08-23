from datetime import timedelta as td
from datetime import datetime as dt
from scipy import interpolate
import pyexiv2 as exiv
import numpy as np
import sqlite3
import csv

db_path = 'data/db/raw_log.db'
dt_testlog = 'test_data/sensus/sensus_test.csv'

def read_gps_log(filepath):
    """Read in a single gps log and keep it in memory so we can search through
    it and find time stamped positions. We will want this to be additive so
    we can read in multiple log files and be able to search through all the 
    timestamped positions.
    
    To be decided:
    - Read in NMEA and GPX or just one? Other formats?
    - In addition to timestamp and position, should we read anything else? Accuracy?
    """
    pass
    
def batch_read_gps_logs(directory):
    """Iteratively use read_gps_log on all files in a directory. Restrict to a 
    range of dates?"""
    pass
    
def depth_from_pressure(mbars):
    """Return a depth (in meters) from a pressure in millibars."""
    return (mbars - 1013.25)/100.52

def read_depth_temp_log(filepath):
    """Read in a single depth / temp csv file  into a sqlite db for persistence 
    and easy searching. Records must have a unique combination of device identifier,
    file number, and datetime stamp. If a conflict is found, the old record will be
    overwritten by the new one. This should insure that duplicates will not be 
    created if a csv file is loaded in multiple times."""
    # Connect to the db
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # Make sure the table is there
    cur.execute("create table if not exists DepthTempLog ( device text, file integer, datetime text, kelvin real, celsius real, mbar integer, depthm real, UNIQUE (device, file, datetime) ON CONFLICT REPLACE)")
    # Read the csv file
    reader = csv.reader(open(filepath,'rb'),delimiter=',')
    # ISO8601 strings ("YYYY-MM-DD HH:MM:SS.SSS"). datetime(year, month, day[, hour[, minute[, second[, microsecond[,tzinfo]]]]])
    for row in reader:
        device = row[1]
        file_id = int(row[2])
        # put the date and time in a datetime object so it can be manipulated
        start_time = dt(int(row[3]),int(row[4]),int(row[5]),int(row[6]),int(row[7]),int(row[8]))
        # I'm not sure if the start time from the logger will be in local time or UTC
        # I suspect it is in local time so I will want to convert to UTC so I can store
        # everything in UTC and avoid screwups related to DST and whatnot
        time_offset = td(seconds=int(row[9]))
        record_time = start_time + time_offset
        time_string = record_time.strftime('%Y-%m-%d %H:%M:%S')
        mbar = int(row[10])
        kelvin = float(row[11])
        celsius = kelvin - 273.15
        depthm = depth_from_pressure(mbar)
        t = (device,file_id,time_string,kelvin,celsius,mbar,depthm)
        # stick it in the table
        cur.execute("insert into DepthTempLog values (?,?,?,?,?,?,?)", t)
    conn.commit()
    cur.close()

def interpolate_depth(t_secs,t1_secs,t2_secs,d1m,d2m):
    """Given depth d1m at time t1_secs and depth d2m at time t2_secs, interpolate
    to find the depth at time t_secs."""
    x = np.array([t1_secs,t2_secs])
    y = np.array([d1m,d2m])
    f = interpolate.interp1d(x,y)
    return f(t_secs)

def get_depth_for_time(dt_obj, verbose=False, reject_threshold=30):
    """For a give datetime object, return the depth from the raw_log db."""
    # select datetime, depthm from DepthTempLog order by abs( strftime('%s','2012-05-01 12:23:53') - strftime('%s',datetime) ) LIMIT 4
    # Connect to the db
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    # make a tuple with the time handed in as seconds so we can pass it to the query
    t = ( dt_obj.strftime('%s'), ) 
    rows = cur.execute("select datetime, depthm from DepthTempLog order by abs( strftime('%s',?) - strftime('%s',datetime) ) LIMIT 2", t).fetchall()
    t1 = dt.strptime(rows[0][0],'%Y-%m-%d %H:%M:%S')
    t1_secs = float( t1.strftime('%s') )
    t2 = dt.strptime(rows[1][0],'%Y-%m-%d %H:%M:%S')
    t2_secs = float( t2.strftime('%s') )
    d1m = rows[0][1]
    d2m = rows[1][1]
    
    times = np.array( t1_secs,t2_secs )
    dt_obj_secs = float( dt_obj.strftime('%s') )
    if ( abs(times.min() - dt_obj_secs) > reject_threshold ) 
    # if dt_obj is between the two closest times, interpolate
    if times.min() <= dt_obj_secs <= times.max():
        return interpolate_depth( dt_obj_secs, t1_secs, t2_secs, d1m, d2m )
    else: # just return the closest
        return d1m
    
