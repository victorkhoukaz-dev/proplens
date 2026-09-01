"""
Unit Test Suite for Statistical Distributions and FantasyPoints Ingestion Engine.
File: tests/unit/test_distributions.py
Milestone: M3 (Requirement R3, Features F10, F11, F12, F13)
"""

import math
from pathlib import Path
import pytest

from app.adapters.fantasypoints import FantasyPointsAdapter, FantasyPointsIngestionEngine
from app.core.distributions import (
    DistributionEngine,
    DistributionResult,
    DistributionType,
)
from app.schemas.projections import PlayerProjection, Position, StatCategory


# ==============================================================================
# 1. CONTINUOUS YARDAGE DISTRIBUTIONS (LOG-NORMAL & CALIBRATED NORMAL)
# ==============================================================================

class TestContinuousYardageDistributions:
    """Test suite for continuous yardage distributions (Log-Normal and Normal)."""

    def test_lognormal_wr_rec_yards_standard(self):
        # M = 62.5, L = 65.5, WR (CV = 0.55)
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=62.5,
            line=65.5,
            position="WR",
            stat_category="rec_yds",
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=0.55,
        )
        assert res.distribution_type == DistributionType.LOG_NORMAL
        assert res.prob_push == 0.0
        assert res.prob_over + res.prob_under == pytest.approx(1.0000, abs=1e-5)
        assert res.prob_under > res.prob_over
        assert res.conditional_prob_over == pytest.approx(res.prob_over, abs=1e-5)
        assert res.fair_decimal_over == pytest.approx(1.0 / res.prob_over, rel=1e-3)

    def test_lognormal_rb_rush_yards_standard(self):
        # M = 68.0, L = 68.5, RB (CV = 0.42)
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=68.0,
            line=68.5,
            position="RB",
            stat_category="rush_yds",
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=0.42,
        )
        assert res.prob_push == 0.0
        assert res.prob_over == pytest.approx(0.4130, rel=1e-3, abs=1e-3)
        assert res.prob_under == pytest.approx(0.5870, rel=1e-3, abs=1e-3)
        assert res.prob_over + res.prob_under == pytest.approx(1.0000, abs=1e-5)

    def test_lognormal_qb_pass_yards_standard(self):
        # M = 268.5, L = 268.5, QB (CV = 0.28)
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=268.5,
            line=268.5,
            position="QB",
            stat_category="pass_yds",
            dist_type=DistributionType.LOG_NORMAL,
        )
        assert res.prob_push == 0.0
        assert res.prob_over == pytest.approx(0.4454, rel=1e-3, abs=1e-3)
        assert res.prob_under == pytest.approx(0.5546, rel=1e-3, abs=1e-3)

    def test_lognormal_te_receiving_skew_property(self):
        # M = 42.0, L = 39.5, TE (CV = 0.58). Median is 36.33 -> P(Over 39.5) < 0.50
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=42.0,
            line=39.5,
            position="TE",
            stat_category="rec_yds",
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=0.58,
        )
        assert res.prob_over == pytest.approx(0.4383, rel=1e-3, abs=1e-3)
        assert res.prob_over < 0.50  # Right skewness property verified

    def test_calibrated_normal_qb_pass_yards_symmetry(self):
        # M = 250.0, L = 250.5, QB (CV = 0.28, sigma = 70.0)
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=250.0,
            line=250.5,
            position="QB",
            stat_category="pass_yds",
            dist_type=DistributionType.CALIBRATED_NORMAL,
            cv_override=0.28,
        )
        assert res.prob_push == 0.0
        assert res.prob_over == pytest.approx(0.4971, rel=1e-3, abs=1e-3)
        assert res.prob_under == pytest.approx(0.5029, rel=1e-3, abs=1e-3)

    def test_custom_cv_override(self):
        res_low_cv = DistributionEngine.evaluate_continuous_prop(
            projection_mean=60.0,
            line=60.5,
            position="WR",
            stat_category="rec_yds",
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=0.30,
        )
        res_high_cv = DistributionEngine.evaluate_continuous_prop(
            projection_mean=60.0,
            line=60.5,
            position="WR",
            stat_category="rec_yds",
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=0.70,
        )
        assert res_low_cv.prob_over != res_high_cv.prob_over

    def test_zero_line_continuous(self):
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=65.0,
            line=0.0,
            position="WR",
            stat_category="rec_yds",
        )
        assert res.prob_over == 1.0
        assert res.prob_under == 0.0
        assert res.prob_push == 0.0
        assert res.fair_decimal_over == 1.0

    def test_continuous_invalid_inputs_raise(self):
        with pytest.raises(ValueError, match="Projection mean must be positive"):
            DistributionEngine.evaluate_continuous_prop(
                projection_mean=0.0,
                line=65.5,
                position="WR",
                stat_category="rec_yds",
            )
        with pytest.raises(ValueError, match="Projection mean must be positive"):
            DistributionEngine.evaluate_continuous_prop(
                projection_mean=-10.0,
                line=65.5,
                position="WR",
                stat_category="rec_yds",
            )
        with pytest.raises(ValueError, match="Line cannot be negative"):
            DistributionEngine.evaluate_continuous_prop(
                projection_mean=65.0,
                line=-5.0,
                position="WR",
                stat_category="rec_yds",
            )
        with pytest.raises(ValueError, match="Unsupported continuous distribution"):
            DistributionEngine.evaluate_continuous_prop(
                projection_mean=65.0,
                line=65.5,
                position="WR",
                stat_category="rec_yds",
                dist_type=DistributionType.POISSON,
            )

    def test_extreme_tails_continuous(self):
        # Deep under tail: line 10.5 on mean 100
        res_deep_under = DistributionEngine.evaluate_continuous_prop(
            projection_mean=100.0,
            line=10.5,
            position="WR",
            stat_category="rec_yds",
        )
        assert res_deep_under.prob_over > 0.99

        # Deep over tail: line 300.5 on mean 40
        res_deep_over = DistributionEngine.evaluate_continuous_prop(
            projection_mean=40.0,
            line=300.5,
            position="WR",
            stat_category="rec_yds",
        )
        assert res_deep_over.prob_over < 0.001


# ==============================================================================
# 2. DISCRETE COUNT DISTRIBUTIONS (POISSON & NEGATIVE BINOMIAL)
# ==============================================================================

class TestDiscreteCountDistributions:
    """Test suite for discrete count props (Anytime TD, Receptions, INTs, Pass TDs)."""

    def test_poisson_anytime_td_standard(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=0.85,
            line=0.5,
            stat_category="anytime_td",
            dist_type=DistributionType.POISSON,
        )
        expected_over = 1.0 - math.exp(-0.85)  # ~0.5726
        expected_under = math.exp(-0.85)       # ~0.4274
        assert res.prob_push == 0.0
        assert res.prob_over == pytest.approx(expected_over, abs=1e-4)
        assert res.prob_under == pytest.approx(expected_under, abs=1e-4)
        assert res.prob_over + res.prob_under == pytest.approx(1.0000, abs=1e-5)

    def test_poisson_passing_interceptions_standard(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=0.65,
            line=0.5,
            stat_category="pass_ints",
            dist_type=DistributionType.POISSON,
        )
        expected_over = 1.0 - math.exp(-0.65)
        assert res.prob_over == pytest.approx(expected_over, abs=1e-4)
        assert res.prob_under == pytest.approx(math.exp(-0.65), abs=1e-4)

    def test_poisson_passing_tds_standard(self):
        # lambda = 1.85, line = 1.5 -> P(Under 1.5) = P(X <= 1) = exp(-1.85)*(1 + 1.85)
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=1.85,
            line=1.5,
            stat_category="pass_tds",
            dist_type=DistributionType.POISSON,
        )
        expected_under = math.exp(-1.85) * (1.0 + 1.85)
        assert res.prob_under == pytest.approx(expected_under, abs=1e-4)
        assert res.prob_over == pytest.approx(1.0 - expected_under, abs=1e-4)

    def test_negbin_anytime_td_overdispersion(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=0.85,
            line=0.5,
            stat_category="anytime_td",
            dist_type=DistributionType.NEGATIVE_BINOMIAL,
            alpha_override=0.22,
        )
        assert res.prob_push == 0.0
        assert res.prob_over > 0.50
        assert res.prob_over + res.prob_under == pytest.approx(1.0000, abs=1e-5)
        # Overdispersion increases zero-count probability vs Poisson
        assert res.prob_under > math.exp(-0.85)

    def test_negbin_wr_receptions_standard(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=5.2,
            line=4.5,
            stat_category="receptions",
            dist_type=DistributionType.NEGATIVE_BINOMIAL,
            alpha_override=0.10,
        )
        assert res.prob_push == 0.0
        assert res.prob_over > 0.50
        assert res.prob_over + res.prob_under == pytest.approx(1.0000, abs=1e-5)

    def test_negbin_passing_tds_standard(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=1.80,
            line=1.5,
            stat_category="pass_tds",
            dist_type=DistributionType.NEGATIVE_BINOMIAL,
            alpha_override=0.12,
        )
        assert res.prob_over > 0.50

    def test_negbin_convergence_to_poisson(self):
        res_poi = DistributionEngine.evaluate_discrete_prop(
            projection_mean=1.85,
            line=1.5,
            stat_category="pass_tds",
            dist_type=DistributionType.POISSON,
        )
        res_nb_limit = DistributionEngine.evaluate_discrete_prop(
            projection_mean=1.85,
            line=1.5,
            stat_category="pass_tds",
            dist_type=DistributionType.NEGATIVE_BINOMIAL,
            alpha_override=1e-7,
        )
        assert res_nb_limit.prob_over == pytest.approx(res_poi.prob_over, abs=1e-4)
        assert res_nb_limit.prob_under == pytest.approx(res_poi.prob_under, abs=1e-4)

    def test_alpha_override_custom_dispersion(self):
        res_low_a = DistributionEngine.evaluate_discrete_prop(
            projection_mean=5.2,
            line=4.5,
            stat_category="receptions",
            dist_type=DistributionType.NEGATIVE_BINOMIAL,
            alpha_override=0.05,
        )
        res_high_a = DistributionEngine.evaluate_discrete_prop(
            projection_mean=5.2,
            line=4.5,
            stat_category="receptions",
            dist_type=DistributionType.NEGATIVE_BINOMIAL,
            alpha_override=0.30,
        )
        assert res_low_a.prob_over != res_high_a.prob_over

    def test_discrete_zero_mean_guard(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=0.0,
            line=0.5,
            stat_category="anytime_td",
        )
        assert res.prob_over == 0.0
        assert res.prob_under == 1.0
        assert res.prob_push == 0.0
        assert res.fair_decimal_under == 1.0
        assert res.fair_decimal_over == 999.0

    def test_discrete_negative_line_raises(self):
        with pytest.raises(ValueError, match="Line cannot be negative"):
            DistributionEngine.evaluate_discrete_prop(
                projection_mean=1.5,
                line=-1.0,
                stat_category="pass_tds",
            )

    def test_poisson_log_space_large_mean(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=25.0,
            line=24.5,
            stat_category="receptions",
            dist_type=DistributionType.POISSON,
        )
        assert 0.0 < res.prob_over < 1.0
        assert res.prob_over + res.prob_under == pytest.approx(1.0000, abs=1e-5)


# ==============================================================================
# 3. PUSH MECHANICS & CONTINUITY CORRECTIONS
# ==============================================================================

class TestPushMechanicsAndContinuity:
    """Test suite for whole-number pushes vs half-point guarantees."""

    def test_half_point_zero_push_guarantee_continuous(self):
        for line in [15.5, 42.5, 65.5, 68.5, 248.5, 268.5]:
            res = DistributionEngine.evaluate_continuous_prop(
                projection_mean=65.0,
                line=line,
                position="WR",
                stat_category="rec_yds",
                dist_type=DistributionType.LOG_NORMAL,
            )
            assert res.prob_push == 0.0
            assert res.prob_over + res.prob_under == pytest.approx(1.0000, abs=1e-5)

    def test_half_point_zero_push_guarantee_discrete(self):
        for line in [0.5, 1.5, 2.5, 4.5, 5.5]:
            res = DistributionEngine.evaluate_discrete_prop(
                projection_mean=5.2,
                line=line,
                stat_category="receptions",
                dist_type=DistributionType.NEGATIVE_BINOMIAL,
            )
            assert res.prob_push == 0.0
            assert res.prob_over + res.prob_under == pytest.approx(1.0000, abs=1e-5)

    def test_integer_yardage_push_probability_continuous(self):
        # M = 65.0, L = 65.0, WR (CV = 0.55) -> Push interval [64.5, 65.5]
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=65.0,
            line=65.0,
            position="WR",
            stat_category="rec_yds",
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=0.55,
        )
        assert res.prob_push > 0.005
        assert res.prob_over + res.prob_under + res.prob_push == pytest.approx(1.0000, abs=1e-5)

    def test_integer_receptions_push_discrete_poisson(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=5.2,
            line=5.0,
            stat_category="receptions",
            dist_type=DistributionType.POISSON,
        )
        assert res.prob_push > 0.10
        assert res.prob_over + res.prob_under + res.prob_push == pytest.approx(1.0000, abs=1e-5)

    def test_integer_receptions_push_discrete_negbin(self):
        res = DistributionEngine.evaluate_discrete_prop(
            projection_mean=5.2,
            line=5.0,
            stat_category="receptions",
            dist_type=DistributionType.NEGATIVE_BINOMIAL,
            alpha_override=0.10,
        )
        assert res.prob_push > 0.10
        assert res.prob_over + res.prob_under + res.prob_push == pytest.approx(1.0000, abs=1e-5)

    def test_conditional_over_under_probability_sum(self):
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=65.0,
            line=65.0,
            position="WR",
            stat_category="rec_yds",
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=0.55,
        )
        expected_cond_over = res.prob_over / (1.0 - res.prob_push)
        expected_cond_under = res.prob_under / (1.0 - res.prob_push)
        assert res.conditional_prob_over == pytest.approx(expected_cond_over, abs=1e-4)
        assert res.conditional_prob_under == pytest.approx(expected_cond_under, abs=1e-4)
        assert res.conditional_prob_over + res.conditional_prob_under == pytest.approx(1.0000, abs=1e-4)

    def test_fair_decimal_odds_inversion_with_push(self):
        res = DistributionEngine.evaluate_continuous_prop(
            projection_mean=65.0,
            line=65.0,
            position="WR",
            stat_category="rec_yds",
            dist_type=DistributionType.LOG_NORMAL,
            cv_override=0.55,
        )
        assert res.fair_decimal_over == pytest.approx(1.0 / res.conditional_prob_over, rel=1e-3)
        assert res.fair_decimal_under == pytest.approx(1.0 / res.conditional_prob_under, rel=1e-3)


# ==============================================================================
# 4. DENSITY CURVE GENERATOR
# ==============================================================================

class TestDensityCurveGeneration:
    """Test suite for Chart.js interactive density curve generation."""

    def test_continuous_density_curve(self):
        curve = DistributionEngine.generate_density_curve(
            projection_mean=65.0,
            line=65.5,
            position="WR",
            stat_category="rec_yds",
            dist_type=DistributionType.LOG_NORMAL,
            points=50,
        )
        assert curve["type"] == "continuous"
        assert len(curve["x"]) == 50
        assert len(curve["y"]) == 50
        assert curve["mean"] == 65.0
        assert curve["line"] == 65.5
        assert all(y >= 0.0 for y in curve["y"])

    def test_discrete_density_curve(self):
        curve = DistributionEngine.generate_density_curve(
            projection_mean=1.85,
            line=1.5,
            stat_category="pass_tds",
            dist_type=DistributionType.NEGATIVE_BINOMIAL,
        )
        assert curve["type"] == "discrete"
        assert len(curve["x"]) > 0
        assert len(curve["y"]) == len(curve["x"])
        assert curve["mean"] == 1.85
        assert curve["line"] == 1.5


# ==============================================================================
# 5. FANTASYPOINTS MULTI-FORMAT INGESTION & SANITIZATION
# ==============================================================================

class TestFantasyPointsIngestion:
    """Test suite for FantasyPoints multi-format parsing and sanitization."""

    @pytest.fixture
    def adapter(self):
        return FantasyPointsAdapter()

    def test_parse_csv_text_comma_delimited(self, adapter):
        csv_text = (
            "Player,Team,Opp,Pos,Pass Att,Pass Cmp,Pass Yds,Pass TD,Pass Int,Rush Att,Rush Yds,Rush TD,Targets,Rec,Rec Yds,Rec TD,Anytime TD,Fantasy Points\n"
            "Patrick Mahomes II,KC,BAL,QB,36.5,24.2,268.5,2.10,0.65,3.8,18.5,0.20,0.0,0.0,0.0,0.00,0.20,20.4\n"
            "Derrick Henry,BAL,KC,RB,0.0,0.0,0.0,0.00,0.00,17.5,78.5,0.80,1.8,1.2,9.0,0.05,0.82,14.6\n"
        )
        projections = adapter.parse_clipboard_text(csv_text)
        assert len(projections) > 0

        # Filter by player
        mahomes_projs = [p for p in projections if "mahomes" in p.canonical_name]
        assert len(mahomes_projs) >= 5
        pass_yd_proj = next(p for p in mahomes_projs if p.stat_category == StatCategory.PASSING_YARDS)
        assert pass_yd_proj.projection_mean == 268.5
        assert pass_yd_proj.team == "KC"
        assert pass_yd_proj.position == "QB"

        henry_projs = [p for p in projections if "henry" in p.canonical_name]
        rush_yd_proj = next(p for p in henry_projs if p.stat_category == StatCategory.RUSHING_YARDS)
        assert rush_yd_proj.projection_mean == 78.5
        assert rush_yd_proj.team == "BAL"
        assert rush_yd_proj.position == "RB"

    def test_parse_tsv_tab_delimited_paste(self, adapter):
        tsv_text = (
            "Player\tTeam\tOpp\tPos\tRec Yds\tRec TD\tReceptions\n"
            "Travis Kelce\tKC\tBAL\tTE\t62.5\t0.55\t5.8\n"
        )
        projections = adapter.parse_clipboard_text(tsv_text)
        assert len(projections) >= 3

        kelce_rec_yds = next(p for p in projections if p.stat_category == StatCategory.RECEIVING_YARDS)
        assert kelce_rec_yds.canonical_name == "travis kelce"
        assert kelce_rec_yds.team == "KC"
        assert kelce_rec_yds.position == "TE"
        assert kelce_rec_yds.projection_mean == 62.5

    def test_parse_whitespace_regex_delimited(self, adapter):
        space_text = (
            "Player    Team   Opp   Pos   Pass Yds   Pass TD\n"
            "Josh Allen    BUF    NYJ   QB    248.0      1.85\n"
        )
        projections = adapter.parse_clipboard_text(space_text)
        assert len(projections) >= 2
        allen_pass_yds = next(p for p in projections if p.stat_category == StatCategory.PASSING_YARDS)
        assert allen_pass_yds.team == "BUF"
        assert allen_pass_yds.projection_mean == 248.0

    def test_header_synonyms_resolution(self, adapter):
        syn_text = (
            "Athlete,Tm,Opponent,PAtt,PYds,PTD,RAtt,RYds,FPTS\n"
            "C.J. Stroud,HOU,IND,35.0,265.0,1.75,2.5,9.0,17.8\n"
        )
        projections = adapter.parse_clipboard_text(syn_text)
        assert len(projections) > 0
        stroud_pass_yds = next(p for p in projections if p.stat_category == StatCategory.PASSING_YARDS)
        assert stroud_pass_yds.team == "HOU"
        assert stroud_pass_yds.projection_mean == 265.0

    def test_dirty_float_sanitization(self, adapter):
        assert adapter.sanitize_float("--") == 0.0
        assert adapter.sanitize_float("N/A") == 0.0
        assert adapter.sanitize_float("nan") == 0.0
        assert adapter.sanitize_float("null") == 0.0
        assert adapter.sanitize_float("* ") == 0.0
        assert adapter.sanitize_float("24.5 (Q)") == 24.5
        assert adapter.sanitize_float("68.0 (IR)") == 68.0
        assert adapter.sanitize_float("1,250.5") == 1250.5
        assert adapter.sanitize_float("-4.0") == -4.0
        assert adapter.sanitize_float("$150") == 150.0
        assert adapter.sanitize_float("+150") == 150.0
        assert adapter.sanitize_float("78.5*") == 78.5
        assert adapter.sanitize_float("") == 0.0
        assert adapter.sanitize_float(None) == 0.0

    def test_composite_anytime_td_calculation(self, adapter):
        row_text = (
            "Player,Team,Opp,Pos,Rush TD,Rec TD\n"
            "Christian McCaffrey,SF,DET,RB,0.85,0.35\n"
        )
        projections = adapter.parse_clipboard_text(row_text)
        atd_proj = next(p for p in projections if p.stat_category == StatCategory.ANYTIME_TD)
        # rush_td (0.85) + rec_td (0.35) = 1.20
        assert atd_proj.projection_mean == pytest.approx(1.20, abs=1e-4)

    def test_automatic_position_inference(self, adapter):
        no_pos_text = (
            "Player,Team,Opp,Pass Att,Pass Yds\n"
            "Patrick Mahomes,KC,BAL,36.5,268.5\n"
        )
        projections = adapter.parse_clipboard_text(no_pos_text)
        assert len(projections) > 0
        assert projections[0].position == "QB"

    def test_empty_and_comment_lines(self, adapter):
        raw_text = "# Weekly Fantasy Projections\n\n\nPlayer,Team,Pos,Pass Yds\n\n"
        projs = adapter.parse_clipboard_text(raw_text)
        assert len(projs) == 0

    def test_parse_file_bytes(self, adapter):
        csv_bytes = b"Player,Team,Opp,Pos,Pass Yds\nPatrick Mahomes,KC,BAL,QB,268.5\n"
        projs = adapter.parse_file(csv_bytes, "test.csv")
        assert len(projs) > 0

    def test_convenience_classmethod(self):
        csv_text = "Player,Team,Opp,Pos,Pass Yds\nPatrick Mahomes,KC,BAL,QB,268.5\n"
        projs = FantasyPointsAdapter.parse_csv_text(csv_text)
        assert len(projs) > 0
        assert FantasyPointsIngestionEngine == FantasyPointsAdapter


# ==============================================================================
# 6. SAMPLE DATA FILE VALIDATION
# ==============================================================================

class TestSampleDataValidation:
    """Test suite validating sample_data/fantasypoints_sample.csv against schema."""

    def test_sample_csv_file_exists_and_parses(self):
        sample_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "fantasypoints_sample.csv"
        assert sample_path.exists()

        adapter = FantasyPointsAdapter()
        with open(sample_path, "rb") as f:
            projections = adapter.parse_file(f.read(), "fantasypoints_sample.csv")

        assert len(projections) >= 30

    def test_sample_all_positions_represented(self):
        sample_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "fantasypoints_sample.csv"
        adapter = FantasyPointsAdapter()
        with open(sample_path, "rb") as f:
            projections = adapter.parse_file(f.read(), "fantasypoints_sample.csv")

        positions = {p.position for p in projections}
        assert "QB" in positions
        assert "RB" in positions
        assert "WR" in positions
        assert "TE" in positions

    def test_sample_canonical_name_and_team_resolution(self):
        sample_path = Path(__file__).resolve().parent.parent.parent / "sample_data" / "fantasypoints_sample.csv"
        adapter = FantasyPointsAdapter()
        with open(sample_path, "rb") as f:
            projections = adapter.parse_file(f.read(), "fantasypoints_sample.csv")

        # Verify Mahomes record
        mahomes = [p for p in projections if "mahomes" in p.canonical_name]
        assert len(mahomes) > 0
        assert mahomes[0].team == "KC"
        assert mahomes[0].position == "QB"

        # Verify all records have valid 2-3 letter team codes
        for p in projections:
            assert len(p.team) in (2, 3)
            assert p.season == 2026
            assert p.projection_mean >= 0.0
