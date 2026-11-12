import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from api.routes.maquila_ordenes import listar_ordenes
from api.routes.ordenes_compra import list_quiebres_historicos


class ListEndpointPayloadTests(unittest.TestCase):
    def test_maquila_orders_empty_list_never_returns_null(self):
        connection = MagicMock()
        connection.execute.return_value.fetchall.return_value = []
        context = MagicMock()
        context.__enter__.return_value = connection

        with patch("api.routes.maquila_ordenes.engine.connect", return_value=context):
            payload = listar_ordenes()

        self.assertEqual(payload, {"data": []})

    def test_purchase_break_history_empty_list_never_returns_null(self):
        context = MagicMock()
        context.__enter__.return_value = MagicMock()

        with (
            patch("api.routes.ordenes_compra.engine.connect", return_value=context),
            patch(
                "api.routes.ordenes_compra.pd.read_sql",
                return_value=pd.DataFrame(),
            ),
        ):
            payload = list_quiebres_historicos()

        self.assertEqual(payload, {"data": []})


if __name__ == "__main__":
    unittest.main()
