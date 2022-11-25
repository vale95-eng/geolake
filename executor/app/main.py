# We have three type of executor:
# - query executor (query)
# - estimate query executor (estimate)
# - catalog info executor (info)
#
# Configuration parameters for the executor:
#    type: query, estimate, catalog
#    dask cluster base ports (if they are not provided the cluster is not created: (e.g. for estimate and catalog info))
#    channel: channel_queue, channel_type, channel_durable
#    catalog path
#    store_path (where to store the query results)
#
# An executor will register to the DB and get a worker id
# if dask cluster base ports are provided, a dask cluster is created
# an executor mush have a unique port for the dask scheduler/dashboard

import os
import json
import pika
import logging
import traceback
from dask.distributed import Client, LocalCluster

from geokube.core.datacube import DataCube

from datastore.datastore import Datastore
from db.dbmanager.dbmanager import DBManager, RequestStatus

from meta import LoggableMeta

_BASE_DOWNLOAD_PATH = "/downloads"


def ds_query(ds_id, prod_id, query, compute, request_id):
    res_path = os.path.join(_BASE_DOWNLOAD_PATH, request_id)
    os.makedirs(res_path, exist_ok=True)
    ds = Datastore()
    kube = ds.query(ds_id, prod_id, query, compute)
    if isinstance(kube, DataCube):
        return kube.persist(res_path)
    else:
        return kube.persist(res_path, zip_if_many=True)


class Executor(metaclass=LoggableMeta):

    _LOG = logging.getLogger("Executor")

    def __init__(self, broker, store_path, cache_path):
        self._datastore = Datastore(cache_path=cache_path)
        self._store = store_path
        broker_conn = pika.BlockingConnection(
            pika.ConnectionParameters(host=broker)
        )
        self._channel = broker_conn.channel()
        self._db = DBManager()

    def create_dask_cluster(self, dask_cluster_opts):
        self._worker_id = self._db.create_worker(
            status="enabled",
            dask_scheduler_port=dask_cluster_opts["scheduler_port"],
            dask_dashboard_address=dask_cluster_opts["dashboard_address"],
        )
        self._LOG.info(
            "creating Dask Cluster with options: `%s`",
            dask_cluster_opts,
            extra={"track_id": self._worker_id},
        )
        dask_cluster = LocalCluster(
            n_workers=dask_cluster_opts["n_workers"],
            scheduler_port=dask_cluster_opts["scheduler_port"],
            dashboard_address=dask_cluster_opts["dashboard_address"],
        )
        self._LOG.info(
            "creating Dask Client...", extra={"track_id": self._worker_id}
        )
        self._dask_client = Client(dask_cluster)

    def query(self, channel, method, properties, body):
        m = body.decode().split("\\")
        request_id = m[0]
        dataset_id = m[1]
        product_id = m[2]
        query = m[3]
        format = m[4]
        self._LOG.debug(
            "executing query: `%s`", body, extra={"track_id": request_id}
        )

        # TODO: estimation size should be updated, too
        self._db.update_request(
            request_id=request_id,
            worker_id=self._worker_id,
            status=RequestStatus.RUNNING,
        )
        self._LOG.debug(
            "submitting job for request", extra={"track_id": request_id}
        )
        future = self._dask_client.submit(
            ds_query,
            ds_id=dataset_id,
            prod_id=product_id,
            query=query,
            compute=False,
            request_id=request_id,
        )
        status = fail_reason = location_path = None
        try:
            self._LOG.debug(
                "attempt to get result for the request",
                extra={"track_id": request_id},
            )
            location_path = future.result()
        except Exception as e:
            self._LOG.error(
                "failed to get result",
                exc_info=True,
                stack_info=True,
                extra={"track_id": request_id},
            )
            status = RequestStatus.FAILED
            fail_reason = f"{type(e)}: {str(e)}"
        else:
            if location_path:
                self._LOG.debug(
                    "updating status and download URI for request",
                    extra={"track_id": request_id},
                )
                status = RequestStatus.DONE
            else:
                self._LOG.warning(
                    "location path is `None` - resulting dataset was empty!",
                    extra={"track_id": request_id},
                )
                status = RequestStatus.FAILED
                fail_reason = (
                    "the query resulted in an empty Dataset. Check your"
                    " request!"
                )
        self._db.update_request(
            request_id=request_id,
            worker_id=self._worker_id,
            status=status,
            location_path=location_path,
            size_bytes=self.get_size(location_path),
            fail_reason=fail_reason,
        )
        self._LOG.debug(
            "acknowledging request", extra={"track_id": request_id}
        )
        channel.basic_ack(delivery_tag=method.delivery_tag)
        self._LOG.debug("request acknowledged", extra={"track_id": request_id})

    def subscribe(self, etype):
        self._LOG.debug(
            "subscribe channel: %s_queue", etype, extra={"track_id": "N/A"}
        )
        self._channel.queue_declare(queue=f"{etype}_queue", durable=True)
        self._channel.basic_qos(prefetch_count=1)
        self._channel.basic_consume(
            queue=f"{etype}_queue", on_message_callback=getattr(self, etype)
        )

    def listen(self):
        while True:
            self._channel.start_consuming()

    def get_size(self, location_path):
        if location_path and os.path.exists(location_path):
            return os.path.getsize(location_path)
        return None


if __name__ == "__main__":

    broker = os.getenv("BROKER", "broker")
    executor_types = os.getenv("EXECUTOR_TYPES", "query").split(",")
    store_path = os.getenv("STORE_PATH", ".")
    cache_path = os.getenv("CACHE_PATH", ".")

    executor = Executor(
        broker=broker, store_path=store_path, cache_path=cache_path
    )
    print("channel subscribe")
    for etype in executor_types:
        if etype == "query":
            dask_cluster_opts = {}
            dask_cluster_opts["scheduler_port"] = int(
                os.getenv("DASK_SCHEDULER_PORT", 8188)
            )
            port = int(os.getenv("DASK_DASHBOARD_PORT", 8787))
            dask_cluster_opts["dashboard_address"] = f":{port}"
            dask_cluster_opts["n_workers"] = int(
                os.getenv("DASK_N_WORKERS", 1)
            )
            executor.create_dask_cluster(dask_cluster_opts)

        executor.subscribe(etype)

    print("waiting for requests ...")
    executor.listen()
