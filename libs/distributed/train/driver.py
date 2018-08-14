#!/usr/bin/env python3
# -*- coding: utf-8 -*-

__author__ = 'mark'
__email__ = 'mark@zamplus.com'


import logging
logger = logging.getLogger(__name__)

import os
# import pyarrow as pa
from libs.env.hdfs import hdfs
import numpy as np
from libs.model.linear_model import LogisticRegression
from conf.conf import CURRENT_WORK_DIR
from conf.hadoop import HDFS_CODE_CACHE
from conf.spark import PYTHON_ENV_CACHE, WORKER_PYTHON
from conf import xlearning
from libs.env.shell import run_cmd
from libs.env.hdfs import hdfs

_training_log_dir = 'eventlog'


class Trainer:
    def __init__(self, job_id, model_conf, runtime_conf):
        self._job_id = job_id
        self._model = model_conf
        self._runtime = runtime_conf

    def train(self, data_name):
        logger.info('[%s] train conf: %s', self._job_id, self._model)

        pos, neg = self._runtime.clk_sample_num, self._runtime.imp_sample_num - self._runtime.clk_sample_num
        base = np.min([pos, neg])
        logger.info('[%s] pos(%d) : neg(%d) = %.1f : %.1f',
                    self._job_id,
                    pos, neg,
                    np.around(pos / base, decimals=1),
                    np.around(neg / base, decimals=1))

        self._xlearning_submit(data_name)

        hdfs_path = os.path.join(self._runtime.hdfs_dir, self._model.name)
        local_ckpt_dir = os.path.join(self._runtime.local_dir, self._model.name)
        hdfs.download_checkpoint(hdfs_path, local_ckpt_dir)

        lr = LogisticRegression(input_dim=self._runtime.input_dim)
        lr.from_checkpoint(local_ckpt_dir)
        return lr

    @staticmethod
    def get_worker_entrance():
        from libs.distributed.train.worker import main_fun_name
        main_file = os.path.relpath(main_fun_name(), CURRENT_WORK_DIR)
        logger.info('worker file: %s', main_file)
        return main_file

    def _xlearning_submit(self, data_name):
        output_path = os.path.join(self._runtime.hdfs_dir, self._model.name)
        if hdfs.exists(output_path):
            hdfs.rm(output_path)

        entrance = self.get_worker_entrance()
        logger.info('model conf: %s', self._model)

        if self._runtime.clk_num < 10000:
            self._model.epoch = 10
            self._model.batch_size = 32
        elif self._runtime.clk_num < 10 * 10000:
            self._model.epoch = 3
            self._model.batch_size = 64
        elif self._runtime.clk_num < 20 * 10000:
            self._model.epoch = 2
            self._model.batch_size = 64
        elif self._runtime.clk_num < 40 * 10000:
            self._model.epoch = 2
            self._model.batch_size = 128

        worker_cmd = ' '.join([
            f'{WORKER_PYTHON} {entrance}',
            f'--job_id={self._job_id}',
            f'--hdfs_dir={self._runtime.hdfs_dir}',
            f'--data={data_name}',
            f'--model={self._model.name}',
            f'--log_dir={_training_log_dir}',
            f'--training_epochs={self._model.epoch}',
            f'--input_dim={self._runtime.input_dim}',
            f'--learning_rate={self._model.learning_rate}',
            f'--batch_size={self._model.batch_size}',
            f'--l2={self._model.l2}',
        ])

        driver_cmd = ' '.join([
            f'{xlearning.XL_SUBMIT}',
            f'--app-type "tensorflow"',
            f'--app-name "CTR-{self._job_id}"',
            f'--launch-cmd "{worker_cmd}"',
            f'--input {self._runtime.hdfs_dir}/{data_name}#{data_name}',
            f'--output {self._runtime.hdfs_dir}/{self._model.name}#{self._model.name}',
            f'--board-logdir {_training_log_dir}',
            f'--cacheArchive {HDFS_CODE_CACHE}#libs,{PYTHON_ENV_CACHE}#python3',
            f'--worker-memory {xlearning.WORKER_MEMORY}',
            f'--worker-num {self._runtime.worker_num}',
            f'--worker-cores {xlearning.WORKER_CORES}',
            f'--ps-memory {xlearning.PS_MEMORY}',
            f'--ps-num {xlearning.PS_NUM}',
            f'--ps-cores {xlearning.PS_CORES}',
            f'--queue default',
            f'--user-path ./python3/bin',
            f'--jars {xlearning.JARS}',
            # '-Duser.timezone=UTC+0800',
            ])
        logger.info(driver_cmd)

        run_cmd(driver_cmd)
        logger.info('finish training process successful.')

