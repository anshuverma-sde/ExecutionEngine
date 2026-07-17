"""Tests for ATM strike calculation and option premium simulation."""
import pytest

from app.features.trading.strike import calculate_atm_strike, simulate_premium


class TestCalculateAtmStrike:
    """calculate_atm_strike rounds to nearest 50 using round-half-up."""

    def test_rounds_down(self):
        assert calculate_atm_strike(22424) == 22400

    def test_rounds_up(self):
        assert calculate_atm_strike(22432) == 22450

    def test_midpoint_rounds_up(self):
        # 22425 / 50 = 448.5 — round-half-up → 449 → 22450
        assert calculate_atm_strike(22425) == 22450

    def test_exact_multiple(self):
        assert calculate_atm_strike(22400) == 22400
        assert calculate_atm_strike(22450) == 22450

    def test_low_price(self):
        assert calculate_atm_strike(100) == 100

    def test_high_price(self):
        assert calculate_atm_strike(50000) == 50000

    def test_returns_int(self):
        result = calculate_atm_strike(22432.75)
        assert isinstance(result, int)

    def test_custom_interval(self):
        assert calculate_atm_strike(1012, interval=100) == 1000
        assert calculate_atm_strike(1051, interval=100) == 1100


class TestSimulatePremium:
    """simulate_premium returns intrinsic + time-value for CE and PE."""

    def test_ce_itm(self):
        # spot > strike → intrinsic = spot - strike
        spot, strike = 22500.0, 22450
        premium = simulate_premium(spot, strike, "CE")
        intrinsic = spot - strike          # 50
        time_value = spot * 0.002          # 45
        assert premium == round(intrinsic + time_value, 2)

    def test_pe_itm(self):
        # spot < strike → intrinsic = strike - spot
        spot, strike = 22400.0, 22450
        premium = simulate_premium(spot, strike, "PE")
        intrinsic = strike - spot          # 50
        time_value = spot * 0.002          # 44.8
        assert premium == round(intrinsic + time_value, 2)

    def test_ce_otm_no_negative_intrinsic(self):
        # spot < strike for CE → intrinsic clamped to 0
        spot, strike = 22400.0, 22450
        premium = simulate_premium(spot, strike, "CE")
        assert premium == round(spot * 0.002, 2)

    def test_pe_otm_no_negative_intrinsic(self):
        # spot > strike for PE → intrinsic clamped to 0
        spot, strike = 22500.0, 22450
        premium = simulate_premium(spot, strike, "PE")
        assert premium == round(spot * 0.002, 2)

    def test_premium_always_positive(self):
        for spot in [20000, 22000, 24000]:
            for opt in ["CE", "PE"]:
                assert simulate_premium(float(spot), 22000, opt) > 0

    def test_returns_two_decimal_places(self):
        p = simulate_premium(22432.0, 22450, "CE")
        assert p == round(p, 2)
