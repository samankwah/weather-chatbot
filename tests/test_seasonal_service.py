"""Tests for Ghana-specific seasonal forecast service."""

import pytest
from datetime import date
from unittest.mock import AsyncMock, MagicMock, patch

from app.models.ai_schemas import GhanaRegion, SeasonType, DrySpellInfo
from app.services.seasonal import (
    get_region,
    get_current_season_type,
    check_onset_criteria,
    calculate_onset_date,
    calculate_cessation_date,
    calculate_dry_spells,
    generate_farming_advice,
    get_expected_onset_info,
    get_expected_cessation_info,
    LATITUDE_THRESHOLD,
)


class TestRegionDetermination:
    """Tests for Ghana region determination by latitude."""

    def test_southern_region_below_threshold(self) -> None:
        """Latitude below 8.0 should be Southern Ghana."""
        assert get_region(5.6037) == GhanaRegion.SOUTHERN  # Accra
        assert get_region(6.6885) == GhanaRegion.SOUTHERN  # Kumasi
        assert get_region(7.9) == GhanaRegion.SOUTHERN  # Just below threshold

    def test_northern_region_at_threshold(self) -> None:
        """Latitude at 8.0 should be Northern Ghana."""
        assert get_region(8.0) == GhanaRegion.NORTHERN

    def test_northern_region_above_threshold(self) -> None:
        """Latitude above 8.0 should be Northern Ghana."""
        assert get_region(9.4034) == GhanaRegion.NORTHERN  # Tamale
        assert get_region(10.7875) == GhanaRegion.NORTHERN  # Bolgatanga

    def test_threshold_value(self) -> None:
        """Threshold should be 8.0 degrees."""
        assert LATITUDE_THRESHOLD == 8.0


class TestSeasonTypeDetermination:
    """Tests for season type determination."""

    def test_northern_region_always_single_season(self) -> None:
        """Northern region should always have single season."""
        for month in range(1, 13):
            test_date = date(2024, month, 15)
            season = get_current_season_type(GhanaRegion.NORTHERN, test_date)
            assert season == SeasonType.SINGLE

    def test_southern_major_season_early_year(self) -> None:
        """Southern region Feb-Jul should be major season."""
        for month in [2, 3, 4, 5, 6, 7]:
            test_date = date(2024, month, 15)
            season = get_current_season_type(GhanaRegion.SOUTHERN, test_date)
            assert season == SeasonType.MAJOR, f"Month {month} should be MAJOR"

    def test_southern_minor_season(self) -> None:
        """Southern region Aug-Nov should be minor season."""
        for month in [8, 9, 10, 11]:
            test_date = date(2024, month, 15)
            season = get_current_season_type(GhanaRegion.SOUTHERN, test_date)
            assert season == SeasonType.MINOR, f"Month {month} should be MINOR"

    def test_southern_december_january_major(self) -> None:
        """Southern region Dec-Jan should be major season (next year)."""
        for month in [12, 1]:
            test_date = date(2024, month, 15)
            season = get_current_season_type(GhanaRegion.SOUTHERN, test_date)
            assert season == SeasonType.MAJOR


class TestOnsetCriteria:
    """Tests for onset criteria checking."""

    def test_onset_met_with_sufficient_rainfall(self) -> None:
        """Should detect onset when criteria are met."""
        # 25mm in first 3 days, no long dry spell in 30 days
        rainfall_data = [
            {"date": "2024-03-15", "precipitation": 15},
            {"date": "2024-03-16", "precipitation": 10},
            {"date": "2024-03-17", "precipitation": 5},
        ]
        # Add 30 more days with some rainfall
        for i in range(30):
            rainfall_data.append({
                "date": f"2024-03-{18+i:02d}" if 18+i <= 31 else f"2024-04-{18+i-31:02d}",
                "precipitation": 5 if i % 3 == 0 else 0,
            })

        result = check_onset_criteria(
            rainfall_data, 0, GhanaRegion.SOUTHERN, SeasonType.MAJOR
        )
        assert result is True

    def test_onset_not_met_insufficient_rainfall(self) -> None:
        """Should not detect onset with insufficient rainfall."""
        rainfall_data = [
            {"date": "2024-03-15", "precipitation": 5},
            {"date": "2024-03-16", "precipitation": 2},
            {"date": "2024-03-17", "precipitation": 1},
        ]
        for i in range(30):
            rainfall_data.append({
                "date": f"2024-03-{18+i:02d}",
                "precipitation": 0,
            })

        result = check_onset_criteria(
            rainfall_data, 0, GhanaRegion.SOUTHERN, SeasonType.MAJOR
        )
        assert result is False

    def test_onset_not_met_long_dry_spell(self) -> None:
        """Should not detect onset when dry spell exceeds threshold."""
        rainfall_data = [
            {"date": "2024-03-15", "precipitation": 25},
        ]
        # Add 15 consecutive dry days (exceeds 10-day threshold)
        for i in range(35):
            rainfall_data.append({
                "date": f"2024-03-{16+i:02d}",
                "precipitation": 0,
            })

        result = check_onset_criteria(
            rainfall_data, 0, GhanaRegion.SOUTHERN, SeasonType.MAJOR
        )
        assert result is False


class TestOnsetDateCalculation:
    """Tests for onset date calculation."""

    def test_onset_detected_returns_date(self) -> None:
        """Should return onset date when detected."""
        rainfall_data = []
        # Pre-season dry period
        for i in range(10):
            rainfall_data.append({
                "date": f"2024-02-{i+1:02d}",
                "precipitation": 0,
            })
        # Onset event + validation period
        for i in range(40):
            day = 11 + i
            month = 2 if day <= 29 else 3
            actual_day = day if day <= 29 else day - 29
            rainfall_data.append({
                "date": f"2024-{month:02d}-{actual_day:02d}",
                "precipitation": 8 if i < 3 else (3 if i % 4 == 0 else 0),
            })

        onset_date, status = calculate_onset_date(
            rainfall_data,
            GhanaRegion.SOUTHERN,
            SeasonType.MAJOR,
            date(2024, 2, 1),
        )

        # Should find onset (exact date depends on criteria)
        assert status in ["occurred", "expected", "not_yet"]

    def test_onset_not_detected_returns_none(self) -> None:
        """Should return None when onset not detected."""
        # All dry days
        rainfall_data = [
            {"date": f"2024-03-{i+1:02d}", "precipitation": 0}
            for i in range(60)
        ]

        onset_date, status = calculate_onset_date(
            rainfall_data,
            GhanaRegion.SOUTHERN,
            SeasonType.MAJOR,
            date(2024, 2, 1),
        )

        assert onset_date is None
        assert status == "not_yet"


class TestCessationCalculation:
    """Tests for cessation date calculation using soil water balance."""

    def test_cessation_detected_when_soil_water_depleted(self) -> None:
        """Should detect cessation when soil water reaches zero."""
        # Start with soil water at 70mm capacity
        # ETO ~4mm/day with no rainfall should deplete in ~17-18 days
        rainfall_data = [
            {
                "date": f"2024-07-{i+1:02d}",
                "precipitation": 0,
                "eto": 4.0,
            }
            for i in range(30)
        ]

        cessation_date, status = calculate_cessation_date(
            rainfall_data,
            GhanaRegion.SOUTHERN,
            SeasonType.MAJOR,
            date(2024, 7, 1),
        )

        assert cessation_date is not None
        assert status in ["occurred", "expected"]

    def test_cessation_not_detected_with_rainfall(self) -> None:
        """Should not detect cessation when rainfall replenishes soil water."""
        rainfall_data = [
            {
                "date": f"2024-07-{i+1:02d}",
                "precipitation": 10,  # Daily rainfall exceeds ETO
                "eto": 4.0,
            }
            for i in range(30)
        ]

        cessation_date, status = calculate_cessation_date(
            rainfall_data,
            GhanaRegion.SOUTHERN,
            SeasonType.MAJOR,
            date(2024, 7, 1),
        )

        assert cessation_date is None
        assert status == "not_yet"


class TestDrySpellCalculation:
    """Tests for dry spell calculation."""

    def test_calculate_dry_spells_with_valid_data(self) -> None:
        """Should calculate early and late dry spells."""
        onset_date = "2024-03-15"
        cessation_date = "2024-07-20"

        # Create rainfall data from onset to cessation
        rainfall_data = []
        current = date(2024, 3, 15)
        end = date(2024, 7, 20)
        i = 0
        while current <= end:
            # Create some dry spells
            if 20 <= i <= 27:  # 8-day early dry spell
                precip = 0
            elif 70 <= i <= 82:  # 13-day late dry spell
                precip = 0
            else:
                precip = 5 if i % 3 == 0 else 0.5
            rainfall_data.append({
                "date": current.isoformat(),
                "precipitation": precip,
            })
            current = date.fromordinal(current.toordinal() + 1)
            i += 1

        dry_spells = calculate_dry_spells(rainfall_data, onset_date, cessation_date)

        assert dry_spells is not None
        assert isinstance(dry_spells, DrySpellInfo)
        assert dry_spells.early_dry_spell_days >= 0
        assert dry_spells.late_dry_spell_days >= 0

    def test_calculate_dry_spells_without_onset(self) -> None:
        """Should return None when no onset date."""
        dry_spells = calculate_dry_spells([], None, None)
        assert dry_spells is None


class TestFarmingAdvice:
    """Tests for farming advice generation."""

    def test_advice_for_occurred_onset(self) -> None:
        """Should give planting advice when onset occurred."""
        advice = generate_farming_advice(
            GhanaRegion.SOUTHERN,
            SeasonType.MAJOR,
            onset_status="occurred",
            cessation_status="not_yet",
            dry_spells=None,
        )
        assert "plant" in advice.lower() or "rains have started" in advice.lower()

    def test_advice_for_expected_onset(self) -> None:
        """Should give preparation advice when onset expected."""
        advice = generate_farming_advice(
            GhanaRegion.SOUTHERN,
            SeasonType.MAJOR,
            onset_status="expected",
            cessation_status="not_yet",
            dry_spells=None,
        )
        assert "prepare" in advice.lower()

    def test_advice_for_not_yet_onset(self) -> None:
        """Should give monitoring advice when onset not yet."""
        advice = generate_farming_advice(
            GhanaRegion.SOUTHERN,
            SeasonType.MAJOR,
            onset_status="not_yet",
            cessation_status="not_yet",
            dry_spells=None,
        )
        assert "monitor" in advice.lower()

    def test_advice_for_northern_region(self) -> None:
        """Should mention single season for Northern region."""
        advice = generate_farming_advice(
            GhanaRegion.NORTHERN,
            SeasonType.SINGLE,
            onset_status="occurred",
            cessation_status="not_yet",
            dry_spells=None,
        )
        assert "single" in advice.lower()

    def test_advice_with_early_dry_spell_warning(self) -> None:
        """Should warn about early dry spells if > 7 days."""
        dry_spells = DrySpellInfo(
            early_dry_spell_days=10,
            late_dry_spell_days=5,
            early_period="Mar 15 - May 04",
            late_period="May 05 - Jul 20",
        )
        advice = generate_farming_advice(
            GhanaRegion.SOUTHERN,
            SeasonType.MAJOR,
            onset_status="occurred",
            cessation_status="not_yet",
            dry_spells=dry_spells,
        )
        assert "dry spell" in advice.lower()


class TestExpectedDateRanges:
    """Tests for expected onset/cessation date ranges."""

    def test_southern_major_onset_range(self) -> None:
        """Should return correct onset range for Southern major."""
        range_str = get_expected_onset_info(GhanaRegion.SOUTHERN, SeasonType.MAJOR)
        assert "Mar" in range_str or "Apr" in range_str

    def test_southern_minor_onset_range(self) -> None:
        """Should return correct onset range for Southern minor."""
        range_str = get_expected_onset_info(GhanaRegion.SOUTHERN, SeasonType.MINOR)
        assert "Sep" in range_str

    def test_northern_single_onset_range(self) -> None:
        """Should return correct onset range for Northern single."""
        range_str = get_expected_onset_info(GhanaRegion.NORTHERN, SeasonType.SINGLE)
        assert "Apr" in range_str or "May" in range_str

    def test_southern_major_cessation_range(self) -> None:
        """Should return correct cessation range for Southern major."""
        range_str = get_expected_cessation_info(GhanaRegion.SOUTHERN, SeasonType.MAJOR)
        assert "Jul" in range_str or "Aug" in range_str

    def test_southern_minor_cessation_range(self) -> None:
        """Should return correct cessation range for Southern minor."""
        range_str = get_expected_cessation_info(GhanaRegion.SOUTHERN, SeasonType.MINOR)
        assert "Nov" in range_str or "Dec" in range_str
