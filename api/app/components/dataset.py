"""Module with tools for dataset and details retrieving"""
import logging
import pika
from typing import Optional

from geoquery.geoquery import GeoQuery
from db.dbmanager.dbmanager import DBManager

from .access import AccessManager
from .meta import LoggableMeta
from ..datastore.datastore import Datastore
from ..decorators import log_execution_time
from ..utils.numeric import make_bytes_readable_dict
from ..exceptions import (
    NoEligibleProductInDatasetError,
    MissingKeyInCatalogEntryError,
    MaximumAllowedSizeExceededError,
)
from ..context import Context
from ..decorators import authenticate, assert_product_exists


class DatasetManager(metaclass=LoggableMeta):
    """Manager that handles dataset present in the geokube-dds catalog"""

    _LOG = logging.getLogger("geokube.DatasetManager")
    _DATASTORE = Datastore(cache_path="/cache")

    @classmethod
    @log_execution_time(_LOG)
    @authenticate(enable_public=True)
    def get_datasets_and_eligible_products_names(
        cls, context: Context
    ) -> list:
        """Realize the logic for the endpoint:

        `GET /datasets/{dataset_id}/{product_id}`

        Get datasets names, their metadata and products names (if eligible for a user).
        If no eligible products are found for a dataset, it is not included.

        Parameters
        ----------
        context : Context
            Context of the current http request

        Returns
        -------
        datasets : list
            A list of datasets information (including metadata and
            eligible products lists)

        Raises
        -------
        MissingKeyInCatalogEntryError
            If the dataset catalog entry does not contain the required key
        """
        cls._LOG.debug("getting all eligible products for datasets...")
        user_roles_names = DBManager().get_user_roles_names(context.user.id)
        datasets = []
        for dataset_id in cls._DATASTORE.dataset_list():
            cls._LOG.debug(
                "getting info and eligible products for `%s`", dataset_id
            )
            dataset_info = cls._DATASTORE.dataset_info(dataset_id=dataset_id)
            try:
                datasets.append(
                    cls._get_dataset_information_from_details_dict(
                        dataset_dict=dataset_info,
                        user_roles_names=user_roles_names,
                        dataset_id=dataset_id,
                        context=context,
                    )
                )
            except NoEligibleProductInDatasetError:
                cls._LOG.debug(
                    "dataset '%s' will not be considered. no"
                    " eligible products for the user with roles"
                    " '%s'",
                    dataset_id,
                    user_roles_names,
                )
                continue
        return datasets

    @classmethod
    @log_execution_time(_LOG)
    @authenticate(enable_public=True)
    @assert_product_exists
    def get_product_metadata(
        cls,
        context: Context,
        dataset_id: str,
        product_id: str,
    ):
        """Realize the logic for the endpoint:

        `GET /datasets/{dataset_id}/{product_id}/metadata`

        Get metadata for the product.

        Parameters
        ----------
        context : Context
            Context of the current http request
        dataset_id : str
            ID of the dataset
        product_id : str
            ID of the product
        """
        return cls._DATASTORE.product_metadata(dataset_id, product_id)

    @classmethod
    @log_execution_time(_LOG)
    @assert_product_exists
    def estimate(
        cls,
        dataset_id: str,
        product_id: str,
        query: GeoQuery,
        unit: Optional[str],
    ):
        """Realize the logic for the nedpoint:

        `POST /datasets/{dataset_id}/{product_id}/estimate`

        Estimate the size of the resulting data.
        No authentication is needed for estimation query.

        Parameters
        ----------
        dataset_id : str
            ID of the dataset
        product_id : str
            ID of the product
        query : GeoQuery
            Query to perform
        unit : str
            One of unit [bytes, kB, MB, GB] to present the result. If `None`,
            unit will be inferred.

        Returns
        -------
        size_details : dict
            Estimated size of  the query in the form:
            ```python
            {
                "value": val,
                "units": units
            }
            ```
        """
        query_bytes_estimation = cls._DATASTORE.query(
            dataset_id, product_id, query, compute=False
        ).nbytes
        return make_bytes_readable_dict(
            size_bytes=query_bytes_estimation, units=unit
        )

    @classmethod
    @log_execution_time(_LOG)
    @authenticate(enable_public=False)
    def retrieve_data_and_get_request_id(
        cls,
        context: Context,
        dataset_id: str,
        product_id: str,
        query: GeoQuery,
        format: str,
    ):
        """Realize the logic for the endpoint:

        `POST /datasets/{dataset_id}/{product_id}/execute`

        Query the data and return the ID of the request.

        Parameters
        ----------
        context : Context
            Context of the current http request
        dataset_id : str
            ID of the dataset
        product_id : str
            ID of the product
        query : GeoQuery
            Query to perform
        format : str
            Format of the data

        Returns
        -------
        request_id : int
            ID of the request

        Raises
        -------
        AuthorizationFailed
        """
        cls._LOG.debug("geoquery: %s", query)
        estimated_size = cls.estimate(dataset_id, product_id, query, "GB").get(
            "value"
        )
        allowed_size = cls._DATASTORE.product_metadata(
            dataset_id, product_id
        ).get("maximum_query_size_gb", 10)
        if estimated_size > allowed_size:
            raise MaximumAllowedSizeExceededError(
                dataset_id=dataset_id,
                product_id=product_id,
                estimated_size_gb=estimated_size,
                allowed_size_gb=allowed_size,
            )
        broker_conn = pika.BlockingConnection(
            pika.ConnectionParameters(host="broker")
        )
        broker_channel = broker_conn.channel()

        request_id = DBManager().create_request(
            user_id=context.user.id,
            dataset=dataset_id,
            product=product_id,
            query=query.original_query_json(),
        )

        # TODO: find a separator; for the moment use "\"
        message = f"{request_id}\\{dataset_id}\\{product_id}\\{query.json()}\\{format}"

        broker_channel.basic_publish(
            exchange="",
            routing_key="query_queue",
            body=message,
            properties=pika.BasicProperties(
                delivery_mode=2,  # make message persistent
            ),
        )
        broker_conn.close()
        return request_id

    @classmethod
    @log_execution_time(_LOG)
    @assert_product_exists
    def get_details_for_product_if_eligible(
        cls,
        dataset_id: str,
        product_id: str,
        context: Context,
    ) -> dict:
        """Realize the logic for the endpoint:

        `GET /datasets/{dataset_id}/{product_id}`

        Get details for the given product indicated by `dataset_id`
        and `product_id` arguments.

        Parameters
        ----------
        dataset_id : str
            ID of the dataset
        product_id : str
            ID of the dataset
        context : Context
            Context of the current http request

        Returns
        -------
        details : dict
            Details for the given product

        Raises
        -------
        AuthorizationFailed
            If user is not authorized for the resources
        """
        cls._LOG.debug(
            "getting details for eligible products of `%s`", dataset_id
        )
        user_roles_names = DBManager().get_user_roles_names(context.user.id)
        details = cls._DATASTORE.product_details(
            dataset_id=dataset_id, product_id=product_id, use_cache=True
        )
        AccessManager.assert_is_role_eligible(
            product_role_name=details["metadata"].get("role"),
            user_roles_names=user_roles_names,
        )
        return details

    @classmethod
    def _get_dataset_information_from_details_dict(
        cls,
        dataset_dict: dict,
        user_roles_names: list[str],
        dataset_id: str,
        context: Context,
    ) -> dict:
        cls._LOG.debug(
            "getting all eligible products for dataset: `%s`", dataset_id
        )
        try:
            eligible_prods = {
                prod_name: prod_info
                for prod_name, prod_info in dataset_dict["products"].items()
                if AccessManager.is_role_eligible_for_product(
                    product_role_name=prod_info.get("role"),
                    user_roles_names=user_roles_names,
                )
            }
        except KeyError as err:
            cls._LOG.error(
                "dataset `%s` does not have products defined",
                dataset_id,
                exc_info=True,
            )
            raise MissingKeyInCatalogEntryError(
                key="products", dataset=dataset_id
            ) from err
        else:
            if len(eligible_prods) == 0:
                cls._LOG.debug(
                    "no eligible products for dataset `%s` for the user"
                    " `%s`. dataset skipped",
                    dataset_id,
                    context.user.id,
                )
                raise NoEligibleProductInDatasetError(
                    dataset_id=dataset_id, user_roles_names=user_roles_names
                )
            dataset_dict["products"] = eligible_prods
        return dataset_dict
