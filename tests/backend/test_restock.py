"""
Tests for restock order API endpoints.
"""
import pytest

import main


@pytest.fixture(autouse=True)
def reset_restock_orders():
    """Keep tests independent of orders created by other tests."""
    main.restock_orders.clear()
    yield
    main.restock_orders.clear()


class TestRestockEndpoints:
    """Test suite for restock-related endpoints."""

    def test_demand_forecasts_have_pricing(self, client):
        """Test that demand forecasts include unit cost and lead time."""
        data = client.get("/api/demand").json()
        assert len(data) > 0

        for forecast in data:
            assert isinstance(forecast["unit_cost"], (int, float))
            assert isinstance(forecast["lead_time_days"], int)
            assert forecast["unit_cost"] > 0
            assert forecast["lead_time_days"] > 0

    def test_get_restock_orders_empty(self, client):
        """Test that no restock orders exist initially."""
        response = client.get("/api/restock-orders")
        assert response.status_code == 200
        assert response.json() == []

    def test_create_restock_order(self, client):
        """Test submitting a restock order computes totals and lead time."""
        forecasts = {f["item_sku"]: f for f in client.get("/api/demand").json()}
        wdg, mtr = forecasts["WDG-001"], forecasts["MTR-304"]

        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "WDG-001", "quantity": 10}, {"sku": "MTR-304", "quantity": 2}],
            "budget": 100000,
        })
        assert response.status_code == 201

        order = response.json()
        assert order["order_number"] == "RST-" + order["created_date"][:4] + "-0001"
        assert order["status"] == "Submitted"
        expected_total = 10 * wdg["unit_cost"] + 2 * mtr["unit_cost"]
        assert abs(order["total_value"] - expected_total) < 0.01
        assert order["lead_time_days"] == max(wdg["lead_time_days"], mtr["lead_time_days"])
        assert "T" in order["expected_delivery"]

    def test_restock_order_ignores_client_prices(self, client):
        """Test that client-supplied prices cannot change the total."""
        forecasts = {f["item_sku"]: f for f in client.get("/api/demand").json()}
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "WDG-001", "quantity": 5, "unit_price": 0.01}],
            "budget": 100000,
        })
        assert response.status_code == 201
        assert abs(response.json()["total_value"] - 5 * forecasts["WDG-001"]["unit_cost"]) < 0.01

    def test_restock_order_unknown_sku(self, client):
        """Test that an unknown SKU is rejected."""
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "NOPE-999", "quantity": 1}], "budget": 1000,
        })
        assert response.status_code == 400
        assert "NOPE-999" in response.json()["detail"]

    def test_restock_order_non_positive_quantity(self, client):
        """Test that zero quantities are rejected."""
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "WDG-001", "quantity": 0}], "budget": 1000,
        })
        assert response.status_code == 400

    def test_restock_order_empty_items(self, client):
        """Test that an order without items is rejected."""
        response = client.post("/api/restock-orders", json={"items": [], "budget": 1000})
        assert response.status_code == 400

    def test_restock_order_over_budget(self, client):
        """Test that an order exceeding the budget is rejected and not stored."""
        response = client.post("/api/restock-orders", json={
            "items": [{"sku": "MTR-304", "quantity": 100}], "budget": 10,
        })
        assert response.status_code == 400
        assert "budget" in response.json()["detail"].lower()
        assert client.get("/api/restock-orders").json() == []

    def test_get_restock_orders_newest_first(self, client):
        """Test that submitted orders are listed newest first."""
        for qty in (1, 2):
            client.post("/api/restock-orders", json={
                "items": [{"sku": "WDG-001", "quantity": qty}], "budget": 100000,
            })

        data = client.get("/api/restock-orders").json()
        assert [o["id"] for o in data] == ["2", "1"]
