import sys
sys.path.append('.')
import json
import logging.config
from conf.conf import JOB_ROOT_DIR
logging.config.dictConfig(json.load(open('conf/logging.json')))

logger = logging.getLogger(__name__)

from  libs.feature.feature_sql import FeatureSql


from datetime import datetime,timedelta
import conf.hadoop as hadoop_conf

from libs.env.spark import spark_session,provide_spark_session
from libs.pack import pack_libs
import random
from  conf import clickhouse
from libs.env import hadoop
from libs.env.hdfs import hdfs
from libs.feature.clickhouse_sparksql_map import replace_map

class FeatureReader:
    def __init__(self,feature,url,executor_num):
        self._feature = feature
        self._url = url
        self._executor_num = executor_num

    @staticmethod
    def jdbc_sql(sql):
        #sql = sql.lstrip("(")
        #sql = sql.rstrip(")")
        sql = f"({sql})"
        return sql


    @provide_spark_session
    def read(self,sql,prop,session=None):
        raw = session.read.jdbc(self._url, sql, properties=prop)
        return raw

    @provide_spark_session
    def readDays(self,start_date,end_date,prop,session=None,**kwargs):
        sqlList = self._feature.get_day_sql_list(start_date, end_date,**kwargs)
        retDf = None
        for s,d in sqlList:

            kwargs[self._feature._data_date_col] = d
            output_file = self._feature.get_output_name(d,**kwargs)
            output_path = hadoop_conf.HDFS_FEATURE_ROOT + '/' + self._feature._name + '/' + output_file
            df = None
            if hdfs.exists(output_path):
                logger.info("feature {name} file {path} is exist! we will use file.".format(name=self._feature._name, path=output_path))
                df = session.read.parquet(output_path)
            else:
                logger.info(
                    "feature {name} file {path} is not exist! we get data from clickhouse.".format(name=self._feature._name, path=output_path))
                s = self.jdbc_sql(s)
                df = session.read.jdbc(self._url, s, properties=prop)
                df.write.parquet(path=output_path,mode='overwrite')
            if not retDf:
                retDf = df
            else:
                retDf =  retDf.union(df)
        return retDf


    def readDaysTempTable(self,start_date,end_date,session=None,**kwargs):
        sqlList = self._feature.get_day_sql_list(start_date, end_date,**kwargs)
        ret_df = None
        hdfs_files_list =[]
        for s,d in sqlList:

            kwargs[self._feature._data_date_col] = d
            output_file = self._feature.get_output_name(d,**kwargs)
            output_path = hadoop_conf.HDFS_FEATURE_ROOT + '/' + self._feature._name + '/' + output_file
            df = None
            if hdfs.exists(output_path):
                logger.info("feature {name} file {path} is exist! we will use file.".format(name=self._feature._name, path=output_path))
                hdfs_files_list.append(output_path)
                df = None
                #df = session.read.parquet(output_path)
            else:
                logger.info(
                    "feature {name} file {path} is not exist! we get data from temp table.".format(name=self._feature._name, path=output_path))
                sql = self._feature._sql.format(**kwargs)
                for k,v in replace_map.items():
                    sql.replace(k,v)
                df = session.sql(sql)
                df.write.parquet(path=output_path,mode='overwrite')
            if not ret_df:
                ret_df = df
            else:
                if df:
                    ret_df = ret_df.union(df).repartition(self._executor_num)

        if not ret_df:
            ret_df = session.read.parquet(*hdfs_files_list)
        else:
            df = session.read.parquet(*hdfs_files_list)
            if df:
                ret_df.union(df).repartition(self._executor_num)

        return ret_df

    def readDaysWithPreSql(self,start_date,end_date,prop,session=None,**kwargs):
        sqlList =[]
        hdfs_files_list = []
        if self._feature._batch_cond:
            for cond in self._feature._batch_cond:
                kwargs.update(cond)
                sl = self._feature.get_day_sql_list(start_date, end_date,pre_sql=True,**kwargs)
                for sql,day in sl:
                    sqlList.append((sql,day,cond))
        else:
            sl = self._feature.get_day_sql_list(start_date, end_date, pre_sql=True, **kwargs)
            for sql, day in sl:
                sqlList.append((sql, day, {}))

        ret_df = None
        for s,d,cond in sqlList:
            kwargs[self._feature._data_date_col] = d
            kwargs.update(cond)
            output_file = self._feature.get_output_name(d,**kwargs) + "_pre"
            output_path = hadoop_conf.HDFS_FEATURE_ROOT + '/' + self._feature._name + '/' + output_file
            df = None
            if hdfs.exists(output_path):
                logger.info("feature {name} file {path} is exist! we will use file.".format(name=self._feature._name, path=output_path))
                hdfs_files_list.append(output_path)
                df = None
                #df = session.read.parquet(output_path)
            else:
                logger.info(
                    "feature {name} file {path} is not exist! we get data from clickhouse.".format(name=self._feature._name, path=output_path))
                s = self.jdbc_sql(s)
                df = session.read.jdbc(self._url, s, properties=prop)
                df.write.parquet(path=output_path,mode='overwrite')
            if not ret_df:
                ret_df = df
            else:
                if df:
                    ret_df = ret_df.union(df)

        if not ret_df:
            ret_df = session.read.parquet(*hdfs_files_list)
        else:
            df = session.read.parquet(*hdfs_files_list)
            if df:
                ret_df.union(df)
        return ret_df

    @provide_spark_session
    def readHours(self,start_date,end_date,prop,session=None,**kwargs):
        sqlList = self._feature.get_hour_sql_list(start_date, end_date,pre_sql=True, **kwargs)
        retDf = None
        for s,d in sqlList:
            kwargs[self._feature._data_date_col] = d
            output_file = self._feature.get_output_name(d,**kwargs)
            output_path = hadoop_conf.HDFS_FEATURE_ROOT + '/' + self._feature._name + '/' + output_file
            df = None
            if hdfs.exists(output_path):
                logger.info("feature {name} file {path} is exist! we will use file.".format(name=self._feature._name, path=output_path))
                df = session.read.parquet(output_path)
            else:
                logger.info(
                    "feature {name} file {path} is not exist! we get data from temp table.".format(name=self._feature._name, path=output_path))

                s = self.jdbc_sql(s)
                df = session.read.jdbc(self._url, s, properties=prop)
                #logger.info(f"count:{df.count()}")
                #logger.info(f"count:{df.show(1)}")
                df.write.parquet(path=output_path,mode='overwrite')
            if not retDf:
                retDf = df
            else:
                retDf =  retDf.union(df)
        return retDf



    @provide_spark_session
    def unionRaw(self,rawDf,start_date,end_date,prop,session=None,**kwargs):

        if self._feature._start_date_offset:
            pre_sql_start_date = start_date + timedelta(self._feature._start_date_offset)
        else:
            pre_sql_start_date = start_date


        if self._feature._pre_sql and  self._feature._temp_table and self._feature._data_time_on_hour:
            logger.info("get feature from hours list...")
            featureDf = self.readHours(start_date, end_date, prop, session=session, **kwargs)
            if self._feature._temp_table_format:
                temp_table_name = self._feature._temp_table_format.format(**kwargs)
                kwargs[self._feature._temp_table] = temp_table_name
            else:
                temp_table_name = self._feature._temp_table

            featureDf.createOrReplaceTempView(temp_table_name)

            sql = self._feature._sql.format(**kwargs)
            featureDf = session.sql(sql)
        elif self._feature._pre_sql and self._feature._temp_table:
            logger.info("get feature from pre sql list...")
            logger.info(f"params:{kwargs}")
            logger.info(f"pre-sql start date:{pre_sql_start_date}  pre-sql end date:{end_date}")
            logger.info(f"sql start date:{start_date}  sql end date:{end_date}")
            featureDf = self.readDaysWithPreSql(pre_sql_start_date,end_date,prop,session=session, **kwargs)
            if self._feature._temp_table_format:
                temp_table_name = self._feature._temp_table_format.format(**kwargs)
                kwargs[self._feature._temp_table] = temp_table_name
            else:
                temp_table_name = self._feature._temp_table

            featureDf.createOrReplaceTempView(temp_table_name)
            if self._feature._once_sql:
                sql = self._feature._sql.format(**kwargs)
                featureDf = session.sql(sql)
            else:
                featureDf = self.readDaysTempTable(start_date, end_date, session=session, **kwargs)
        else:
            logger.info("get feature from days list...")
            featureDf = self.readDays(start_date,end_date,prop,session=session,**kwargs)

        raw = rawDf.alias("raw")
        feature = featureDf.alias("feature")
        joinedDf = raw.join(feature,self._feature._keys,"left")
        return joinedDf







# database = 'model'
#
# URL = f'jdbc:clickhouse://{random.choice(clickhouse.hosts)}/{database}'
#
# #URL = 'test'
# if __name__ == '__main__':
#     logger.info("start main")
#
#     pack_libs()
#     logger.info("end main")
#     sql_tmp =  ctr_feature.get_ctr_feature()
#
#     session = spark_session("testFeature",3,None)
#
#
#     #feature = feature_sql(["Id_Zid,Media_VendorId,EventDate"],sql_tmp,"[{account},{vendor}]","target_day")
#     feature = FeatureSql("compaign_last30_ctr",["Id_Zid","Media_VendorId","Bid_CompanyId","EventDate"], ["a{account}_{vendor}_last14_imp","a{account}_{vendor}_last14_clk"],sql_tmp,
#                           "target_day","a{account}_v{vendor}_t{target_day:%Y%m%d}")
#
#
#     factory = FeatureReader(feature,URL)
#     args = {'account':12, 'vendor':24}
#
#     raw = factory.read(ctr_feature.get_raw_sql(),clickhouse.ONE_HOST_CONF,session=session)
#     raw.show()
#
#     unioned =  factory.unionRaw(raw,datetime.now() -timedelta(days=10),datetime.now()-timedelta(days=9) ,clickhouse.ONE_HOST_CONF,session=session,**args)
#     unioned.show()
#
#
#     #raw =  factory.read(session=session)
#     #print(raw)
