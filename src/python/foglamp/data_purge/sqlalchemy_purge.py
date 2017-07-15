"""
Description: Based on FOGL-200 (https://docs.google.com/document/d/1GdMTerNq_-XQuAY0FJNQm09nbYQSjZudKJhY8x5Dq8c/edit) 
    the purge process is suppose to remove data based on either a user_id, or an X amount of time back depending on
    whether or not the configuration (config.json) requires to retain data that has not been sent to the Pi System.
    
    Given that the code is dependent on configuration files, sending data to Pi, and connecting to the database, 
    I have "hard-coded" those dependencies with the use of extra methods, and files. This includes things like: 
    get_nth_id which updates the config file with a 'random' last ID that was sent to Pi, and the main which also 
    as a scheduler process. 
    
     Specifically the purge process (purge_process_function) does the following: 
     - Based on the configuration file (retainUnsent) it either removes by the lastID 
        (in which case retainUnsent is True), or by age (timestamp)
     - Calculate vital information regarding the purge, and record it in the logs file
      
Based on the way things are currently being done, both the logs file (logs.json), and configurations file (config.json)
will be replaced either database tables, or some other kind of file. 
"""
import datetime
import json
import os
import random
import sqlalchemy
import sqlalchemy.dialects.postgresql
import sys
import time


__author__ = "Ori Shadmon"
__copyright__ = "Copyright (c) 2017 OSI Soft, LLC"
__license__ = "Apache 2.0"
__version__ = "2"


# Set variables for connecting to database
_user = "foglamp"
_db_user = "foglamp"
_host = "192.168.0.182"
_db = "foglamp"

# Create Connection
__engine__ = sqlalchemy.create_engine('postgres://%s:%s@%s/%s' % (_db_user, _user, _host, _db),  pool_size=20,  max_overflow=0)
__conn__ = __engine__.connect()

# Important files
config_file = 'config.json'

# Table purge against
__readings_table__ = sqlalchemy.Table('readings', sqlalchemy.MetaData(),
                                  sqlalchemy.Column('id', sqlalchemy.BIGINT, primary_key=True),
                                  sqlalchemy.Column('asset_code', sqlalchemy.VARCHAR(50)),
                                  sqlalchemy.Column('read_key', sqlalchemy.dialects.postgresql.UUID,
                                                    default='00000000-0000-0000-0000-000000000000'),
                                  sqlalchemy.Column('reading', sqlalchemy.dialects.postgresql.JSON, default='{}'),
                                  sqlalchemy.Column('user_ts', sqlalchemy.TIMESTAMP(6),
                                                    default=time.strftime('%Y-%m-%d %H:%M:%S',
                                                                          time.localtime(time.time()))),
                                  sqlalchemy.Column('ts', sqlalchemy.TIMESTAMP(6),
                                                    default=time.strftime('%Y-%m-%d %H:%M:%S',
                                                                          time.localtime(time.time()))))


"""logging table is instead of the log. After much thought, in addition to the discussed information the table also 
includes the following: 
    -> table to specify which table has been purged, since the process could occur in multiple tables 
    -> total_unsent_rows specifies the total number of unsent rows that existed within range prior to the purge. 
    based off that, and unsent_rows_removed one can calcualte how many (unsent rows) remain.
"""
__logging_table__ = sqlalchemy.Table('purge_logging', sqlalchemy.MetaData(),
                                     sqlalchemy.Column('id', sqlalchemy.BIGINT, primary_key=True, autoincrement=True),
                                     sqlalchemy.Column('table', sqlalchemy.VARCHAR(255),
                                                       default=__readings_table__.name),
                                     sqlalchemy.Column('start_time', sqlalchemy.VARCHAR(255),
                                                       default=sqlalchemy.func.current_timestamp),
                                     sqlalchemy.Column('end_time', sqlalchemy.VARCHAR(255),
                                                       default=sqlalchemy.func.current_timestamp),
                                     sqlalchemy.Column('total_rows_removed', sqlalchemy.INTEGER, default=0),
                                     sqlalchemy.Column('total_unsent_rows', sqlalchemy.INTEGER, default=0),
                                     sqlalchemy.Column('total_unsent_rows_removed', sqlalchemy.INTEGER, default=0),
                                     sqlalchemy.Column('total_failed_to_remove', sqlalchemy.INTEGER, default=0))

"""Methods that support the purge process. For the most part, theses methods would be replaced by either a scheduler,  
a database API interface,  and/or proper configuration methodology. 
"""


def convert_timestamp(set_time: str) -> datetime.timedelta:
    """Convert "age" in config file to timedelta. If only an integer is specified,  then 
        the code assumes that it is already in minutes (ie age:1 means wait 1 minute) 
    Args:
        set_time (str): Newest amount of  time back to delete
    Returns:
        converted set_time to datetime.timedelta value
    """
    if set_time.isdigit():
        return datetime.timedelta(minutes=int(set_time))
    time_dict = {}
    tmp = 0

    for value in set_time.split(" "):
        if value.isdigit() is True:
            tmp = int(value)
        else:
            time_dict[value] = tmp

    time_in_sec = datetime.timedelta(seconds=0)
    time_in_min = datetime.timedelta(minutes=0)
    time_in_hr = datetime.timedelta(hours=0)
    time_in_day = datetime.timedelta(days=0)

    for key in time_dict.keys():
        if 'sec' in key:
            time_in_sec = datetime.timedelta(seconds=time_dict[key])
        elif 'min' in key:
            time_in_min = datetime.timedelta(minutes=time_dict[key])
        elif ('hr' in key) or ('hour' in key):
            time_in_hr = datetime.timedelta(hours=time_dict[key])
        elif ('day' in key) or ('dy' in key):
            time_in_day = datetime.timedelta(days=time_dict[key])
    return time_in_sec+time_in_min+time_in_hr+time_in_day


def convert_sleep(set_time: str) -> int:
    """Convert "wait" in config file to seconds in order to know how long to wait until next purge process. 
        This method would potentially be replaced by the scheduler 
    Args:
        set_time (str): A string of "values" specified in the config to declare how long to wait till next purge

    Returns:
        integer (of seconds) based on wait in config 
    """
    if set_time.isdigit():
        return int(set_time)
    time_dict = {}
    tmp = 0
    for value in set_time.split(" "):
        if value.isdigit() is True:
            tmp = int(value)
        else:
            time_dict[value] = tmp
    time_in_sec = 0
    time_in_min = 0
    time_in_hr = 0
    time_in_dy = 0
    for key in time_dict:
        if "sec" in key:
            time_in_sec = time_dict[key]
        elif "min" in key:
            time_in_min = 60 * time_dict[key]
        elif ("hour" in key) or ("hr" in key):
            time_in_hr = 60 * 60 * time_dict[key]
        elif ("day" in key) or ("dy" in key):
            time_in_dy = 60 * 60 * 24 * time_dict[key]
        else:
            print("Error: Invalid Value(s) in config file")
            sys.exit()
    return time_in_sec+time_in_min+time_in_hr+time_in_dy


def execute_command_with_return_value(stmt: str) -> int:
    """Imitate connection to postgres that returns result.    
    Args:
        stmt (str): generated SQL query   
    Returns:
        Returns the first value in the result set
    """
    query_result = __conn__.execute(stmt)
    return query_result.fetchall()[0][0]


def execute_command_without_return_value(stmt: str) -> None:
    """Imitate connection to Postgres and a query that doesn't generate results
    Args:
        stmt (str): DELETE stmt 
    """
    __conn__.execute(stmt)
    __conn__.execute("commit")


def get_nth_id() -> None:
    """Update the config file to have row ID somewhere within the oldest 100 rows.
    
    This method would potentially be replaced by the communication with the Pi System which will be
    aware of what was the last ID sent to the Pi System. 
    Returns: 
        Method doesn't return anything
    """
    rand = random.randint(1, 100)

    stmt = "SELECT id FROM (SELECT id FROM readings ORDER BY id ASC LIMIT %s)t ORDER BY id DESC LIMIT 1"
    row_id = int(execute_command_with_return_value(stmt % rand))

    with open(config_file, 'r') as conf:
        config_info = json.load(conf)

    config_info["lastID"] = row_id
    open(config_file, 'w').close()
    with open(config_file, 'r+') as conf:
        conf.write(json.dumps(config_info))

def create_purge_logging_table() -> None:
    """Create logging table for purge process. 
    While it is prefered not to do try/catch, this was the fastest way to execute "DROP IF EXSITS" 
    """
    try:
        __logging_table__.drop(__engine__)
    except sqlalchemy.exc.ProgrammingError:
        pass
    __logging_table__.create(__engine__)

"""The actual purge process 
"""


def purge_process_function(table_name) -> int:
    """The actual process read the configuration file, and based off the information in it does the following:
    1. Gets previous information found in log file
    2. Based on the configurations, call the DELETE command to purge the data
    3. Calculate relevant information kept in logs
    4. Based on the configuration calculates how long to wait until next purge, and returns that

    Args:
        table_name (SQLAlchemy.Table): The name of the table queries run against
    Returns:
        Amount of time until next purge process
    """

    # Reload config (JSON File) - age,  enabled,  wait,  pi_date
    with open(config_file, 'r') as conf:
        config = json.load(conf)

    data = {}
    purge_status = {}

    if config['enabled'] is True:  # meaning that config info is authorizing the purge
        start_time = datetime.datetime.fromtimestamp(time.time())

        age_timestamp = datetime.datetime.strftime(start_time - convert_timestamp(
            set_time=config['age']), '%Y-%m-%d %H:%M:%S.%f')
        start_time = start_time.strftime('%Y-%m-%d %H:%M:%S')

        last_connection_id = config['lastID']

        # Number of rows exist at the point of calling purge
        total_count_query = sqlalchemy.select([sqlalchemy.func.count()]).select_from(table_name).where(
            table_name.c.ts < start_time)
        total_count_before = int(execute_command_with_return_value(total_count_query))

        # Number of unsent rows
        number_sent_rows_query = sqlalchemy.select([sqlalchemy.func.count()]).select_from(table_name).where(
            table_name.c.id > last_connection_id).where(table_name.c.ts < start_time)

        unsent_rows_before = int(execute_command_with_return_value(number_sent_rows_query))

        """Time purge process starts
        If unsent data is retained, then the WHERE condition is against the last sent ID
        """
        failed_removal_count = 0
        if config['retainUnsent'] is True:
            delete_query = sqlalchemy.delete(table_name).where(table_name.c.id <= last_connection_id).where(
                table_name.c.ts <start_time)
            execute_command_without_return_value(delete_query)

            # Number of rows that were expected to get removed, but weren't
            failed_removal_query = sqlalchemy.select([sqlalchemy.func.count()]).select_from(
                table_name).where(table_name.c.id <= last_connection_id).where(
                table_name.c.ts <start_time)
            failed_removal_count = int(execute_command_with_return_value(failed_removal_query))

        # If unsent data is not retained, then the WHERE condition is against the age
        else:
            row_id = int(execute_command_with_return_value(sqlalchemy.select([table_name.c.id]).select_from(table_name).where(
                table_name.c.ts <= age_timestamp).order_by(table_name.c.id.desc()).limit(1)))

            delete_query = sqlalchemy.delete(table_name).where(table_name.c.id <= row_id).where(
                table_name.c.ts < start_time)
            execute_command_without_return_value(delete_query)

            # Number of rows that were expected to get removed, but weren't
            failed_removal_query = sqlalchemy.select([sqlalchemy.func.count()]).select_from(
                table_name).where(table_name.c.id <= last_connection_id).where(
                table_name.c.ts < start_time)
            failed_removal_count = int(execute_command_with_return_value(failed_removal_query))

        unsent_rows_after = int(execute_command_with_return_value(number_sent_rows_query))
        unsent_rows_removed = unsent_rows_before - unsent_rows_after


        total_count_after = int(execute_command_with_return_value(sqlalchemy.select(
            [sqlalchemy.func.count()]).select_from(table_name).where(table_name.c.ts <start_time)))
        total_rows_removed = total_count_before - total_count_after

        # Number of unsent rows removed
        unsent_rows_after = int(execute_command_with_return_value(number_sent_rows_query))

        unsent_rows_removed = unsent_rows_before - unsent_rows_after
        if unsent_rows_removed < 0:
            unsent_rows_removed = 0
        # Time  purge process finished
        end_time = datetime.datetime.fromtimestamp(time.time()).strftime('%Y-%m-%d %H:%M:%S')
        inst_stmt = __logging_table__.insert().values(table=table_name.name, start_time=start_time, end_time=end_time,
                                                total_rows_removed=total_rows_removed,
                                                total_unsent_rows_removed=unsent_rows_removed,
                                                total_unsent_rows = unsent_rows_before,
                                                total_failed_to_remove=failed_removal_count)
        execute_command_without_return_value(inst_stmt)
    """
    __logging_table__ = sqlalchemy.Table('purge_logging', sqlalchemy.MetaData(),
                                     sqlalchemy.Column('id', sqlalchemy.BIGINT, primary_key=True, autoincrement=True),
                                     sqlalchemy.Column('table', sqlalchemy.VARCHAR(255),
                                                       default=__readings_table__.name),
                                     sqlalchemy.Column('start_time', sqlalchemy.VARCHAR(255),
                                                       default=sqlalchemy.func.current_timestamp),
                                     sqlalchemy.Column('end_time', sqlalchemy.VARCHAR(255),
                                                       default=sqlalchemy.func.current_timestamp),
                                     sqlalchemy.Column('total_rows_removed', sqlalchemy.INTEGER, default=0),
                                     sqlalchemy.Column('total_unsent_rows', sqlalchemy.INTEGER, default=0),
                                     sqlalchemy.Column('total_unsent_rows_removed', sqlalchemy.INTEGER, default=0),
                                     sqlalchemy.Column('total_failed_to_remove', sqlalchemy.INTEGER, default=0))

    """


    return convert_sleep(config['wait'])

"""
The main,  which would be replaced by the scheduler 
"""
if __name__ == '__main__':
    """The main / scheduler creates the logs.json file,  and executes the purge (returning how long to wait)
    till the next purge execution. Noticed that the purge process expects the table,  and config file. 
    This is because (theoretically) purge  would be executed on multiple tables,  where each table could 
    have its own configs. 
        
    As of now,  the example shows only 1 table,  but can be rewritten to show multiple tables without too much
    work. 
    """
    create_purge_logging_table()

    while True:
        get_nth_id()
        wait = purge_process_function(table_name=__readings_table__)
        time.sleep(wait)


