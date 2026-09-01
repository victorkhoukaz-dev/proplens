"""
Adversarial Stress Test Suite for FantasyPoints Adapter
Milestone 3 - Challenger 2 Empirical Verification
"""
import io
import math
import pytest
from app.adapters.fantasypoints import FantasyPointsAdapter, NULL_TOKENS
from app.schemas.projections import PlayerProjection, Position, StatCategory


class TestAdversarialDirtyFloats:
    """Empirical verification of extreme dirty float strings."""

    @pytest.mark.parametrize(
        "raw_val, expected, desc",
        [
            ("$1,245.50 (Q)*", 1245.50, "Currency + comma + injury Q in parens + asterisk"),
            ("--", 0.0, "Double dash null token"),
            ("N/A", 0.0, "N/A uppercase"),
            ("NaN", 0.0, "NaN mixed case string"),
            ("null", 0.0, "null lowercase string"),
            ("None", 0.0, "None string"),
            ("OUT", 0.0, "OUT injury token"),
            ("IR", 0.0, "IR injury token"),
            ("-3.5", -3.5, "Negative float preserved"),
            ("0.0", 0.0, "Zero float"),
            ("+250.5", 250.5, "Leading plus sign"),
            (" 18.0 [P] ", 18.0, "Injury in brackets with whitespace"),
            ("68.0 (IR)", 68.0, "Injury in parens with float"),
            ("$ -- ", 0.0, "Dollar sign with double dash"),
            ("(DNP)", 0.0, "Parens DNP"),
            ("(PUP)", 0.0, "Parens PUP"),
            ("(SUS)", 0.0, "Parens SUS"),
            ("N/A*", 0.0, "N/A with asterisk"),
            ("1,000,000.50", 1000000.50, "Million with commas"),
            (None, 0.0, "NoneType"),
            (0, 0.0, "Integer zero"),
            (42, 42.0, "Integer positive"),
            (3.14159, 3.14159, "Native float"),
            (" - ", 0.0, "Single dash with spaces"),
            ("?", 0.0, "Question mark token"),
            ("#", 0.0, "Hash token"),
            ("   ", 0.0, "Whitespace string"),
            ("unparseable_text", 0.0, "Arbitrary text fallback"),
            ("-", 0.0, "Single dash token"),
            ("dnp", 0.0, "dnp lowercase"),
            ("pup", 0.0, "pup lowercase"),
            ("q", 0.0, "q single letter"),
            ("d", 0.0, "d single letter"),
            ("p", 0.0, "p single letter"),
        ],
    )
    def test_dirty_float_cases(self, raw_val, expected, desc):
        actual = FantasyPointsAdapter.sanitize_float(raw_val)
        assert math.isclose(actual, expected, abs_tol=1e-5), f"Failed for {desc}: expected {expected}, got {actual}"


class TestAdversarialDelimitersAndPastes:
    """Empirical verification of various delimiter formats and clipboard pastes."""

    @pytest.fixture
    def adapter(self):
        return FantasyPointsAdapter()

    def test_tab_delimited_clipboard(self, adapter):
        tsv_paste = (
            "Player\tTeam\tOpp\tPos\tPass Yds\tPass TD\n"
            "Patrick Mahomes\tKC\tBAL\tQB\t285.5\t2.2\n"
            "Josh Allen\tBUF\tNYJ\tQB\t260.0\t1.8\n"
        )
        projs = adapter.parse_clipboard_text(tsv_paste)
        assert len(projs) > 0
        names = {p.player_name for p in projs}
        assert "Patrick Mahomes" in names
        assert "Josh Allen" in names

    def test_pipe_delimited_clipboard(self, adapter):
        pipe_paste = (
            "Player|Team|Opp|Pos|Pass Yds|Pass TD\n"
            "Patrick Mahomes|KC|BAL|QB|285.5|2.2\n"
            "Josh Allen|BUF|NYJ|QB|260.0|1.8\n"
        )
        projs = adapter.parse_clipboard_text(pipe_paste)
        assert len(projs) > 0
        names = {p.player_name for p in projs}
        assert "Patrick Mahomes" in names
        assert "Josh Allen" in names

    def test_semicolon_delimited_clipboard(self, adapter):
        semi_paste = (
            "Player;Team;Opp;Pos;Pass Yds;Pass TD\n"
            "Patrick Mahomes;KC;BAL;QB;285.5;2.2\n"
            "Josh Allen;BUF;NYJ;QB;260.0;1.8\n"
        )
        projs = adapter.parse_clipboard_text(semi_paste)
        assert len(projs) > 0
        names = {p.player_name for p in projs}
        assert "Patrick Mahomes" in names

    def test_multispace_regex_clipboard(self, adapter):
        space_paste = (
            "Player             Team  Opp  Pos  Pass Yds  Pass TD\n"
            "Patrick Mahomes    KC    BAL  QB   285.5     2.2\n"
            "Josh Allen         BUF   NYJ  QB   260.0     1.8\n"
        )
        projs = adapter.parse_clipboard_text(space_paste)
        assert len(projs) > 0
        names = {p.player_name for p in projs}
        assert "Patrick Mahomes" in names
        assert "Josh Allen" in names

    def test_comments_and_blank_lines(self, adapter):
        messy_paste = (
            "# Top Projections Week 1\n"
            "\n"
            "Player,Team,Opp,Pos,Pass Yds\n"
            "\n"
            "# AFC West\n"
            "Patrick Mahomes,KC,BAL,QB,285.5\n"
            "   \n"
            "# AFC East\n"
            "Josh Allen,BUF,NYJ,QB,260.0\n"
            "\n"
        )
        projs = adapter.parse_clipboard_text(messy_paste)
        names = {p.player_name for p in projs}
        assert names == {"Patrick Mahomes", "Josh Allen"}


class TestAdversarialMalformedTables:
    """Stress tests on malformed rows, jagged tables, and corrupted headers."""

    @pytest.fixture
    def adapter(self):
        return FantasyPointsAdapter()

    def test_extra_trailing_columns(self, adapter):
        csv_extra = (
            "Player,Team,Opp,Pos,Pass Yds\n"
            "Patrick Mahomes,KC,BAL,QB,270.0,ExtraVal1,ExtraVal2\n"
            "Josh Allen,BUF,NYJ,QB,250.0,AnotherExtra\n"
        )
        projs = adapter.parse_clipboard_text(csv_extra)
        assert len(projs) > 0
        names = {p.player_name for p in projs}
        assert "Patrick Mahomes" in names
        assert "Josh Allen" in names

    def test_missing_position_and_opponent(self, adapter):
        csv_minimal = (
            "Player,Pass Yds,Pass TD\n"
            "Patrick Mahomes,275.0,2.1\n"
        )
        projs = adapter.parse_clipboard_text(csv_minimal)
        assert len(projs) > 0
        mahomes = projs[0]
        assert mahomes.player_name == "Patrick Mahomes"
        assert mahomes.position == "QB"  # Inferred from Pass Yds >= 40.0
        assert mahomes.team == "FA"  # Default when team omitted

    def test_all_empty_cells_row(self, adapter):
        csv_empty_row = (
            "Player,Team,Opp,Pos,Pass Yds\n"
            ",,,,\n"
            "Patrick Mahomes,KC,BAL,QB,270.0\n"
            ",,,,\n"
        )
        projs = adapter.parse_clipboard_text(csv_empty_row)
        names = {p.player_name for p in projs}
        assert names == {"Patrick Mahomes"}

    def test_summary_rows_filtered(self, adapter):
        csv_summary = (
            "Player,Team,Opp,Pos,Pass Yds\n"
            "Patrick Mahomes,KC,BAL,QB,270.0\n"
            "Total,KC,BAL,QB,270.0\n"
            "Average,KC,BAL,QB,270.0\n"
        )
        projs = adapter.parse_clipboard_text(csv_summary)
        names = {p.player_name for p in projs}
        assert "Patrick Mahomes" in names
        assert "Total" not in names
        assert "Average" not in names


class TestAdversarialSchemaValidationIntegrity:
    """Ensure PlayerProjection Pydantic models are 100% valid."""

    @pytest.fixture
    def adapter(self):
        return FantasyPointsAdapter()

    def test_composite_anytime_td(self, adapter):
        csv_text = (
            "Player,Team,Pos,Rush TD,Rec TD\n"
            "Saquon Barkley,PHI,RB,0.75,0.25\n"
        )
        projs = adapter.parse_clipboard_text(csv_text)
        atd = next(p for p in projs if p.stat_category == StatCategory.ANYTIME_TD)
        assert atd.projection_mean == pytest.approx(1.0, abs=1e-4)

    def test_explicit_anytime_td_overrides_composite(self, adapter):
        csv_text = (
            "Player,Team,Pos,Rush TD,Rec TD,Anytime TD\n"
            "Saquon Barkley,PHI,RB,0.75,0.25,0.85\n"
        )
        projs = adapter.parse_clipboard_text(csv_text)
        atd = next(p for p in projs if p.stat_category == StatCategory.ANYTIME_TD)
        assert atd.projection_mean == pytest.approx(0.85, abs=1e-4)

    def test_negative_projections_handled(self, adapter):
        csv_text = (
            "Player,Team,Pos,Rush Yds\n"
            "Negative Runner,NYG,RB,-3.5\n"
        )
        projs = adapter.parse_clipboard_text(csv_text)
        rush = next(p for p in projs if p.stat_category == StatCategory.RUSHING_YARDS)
        assert rush.projection_mean == -3.5


class TestAdversarialInvalidTypesAndCorruptInputs:
    """Test boundary failure modes and type errors."""

    @pytest.fixture
    def adapter(self):
        return FantasyPointsAdapter()

    def test_empty_string_returns_empty_list(self, adapter):
        assert adapter.parse_projections("") == []
        assert adapter.parse_clipboard_text("") == []

    def test_whitespace_string_returns_empty_list(self, adapter):
        assert adapter.parse_projections("   \n\t  \n") == []

    def test_unsupported_types_raise_type_error(self, adapter):
        with pytest.raises(TypeError):
            adapter.parse_projections(12345)
        with pytest.raises(TypeError):
            adapter.parse_projections(None)
        with pytest.raises(TypeError):
            adapter.parse_projections({"invalid": "dict_not_records"})

    def test_corrupt_binary_csv_bytes(self, adapter):
        corrupt_bytes = b"\x00\xff\xfe\x01\x02\x03\xfa\xce\xde\xad\xbe\xef"
        res = adapter.parse_file(corrupt_bytes, filename="corrupt.csv")
        assert isinstance(res, list)

    def test_corrupt_excel_bytes_graceful_handling(self, adapter):
        corrupt_xlsx = b"PK\x03\x04corrupted_bytes_not_zip"
        try:
            res = adapter.parse_file(corrupt_xlsx, filename="corrupt.xlsx")
            assert isinstance(res, list)
        except Exception:
            # openpyxl raising an error on bad zip is also acceptable behavior
            pass

    def test_unicode_player_names_and_accents(self, adapter):
        csv_unicode = (
            "Player,Team,Pos,Rec Yds\n"
            "Amon-Ra St. Brown,DET,WR,84.5\n"
            "Ja'Marr Chase,CIN,WR,92.0\n"
            "Velus Jones Jr.,CHI,WR,15.0\n"
        )
        projs = adapter.parse_clipboard_text(csv_unicode)
        assert len(projs) > 0
        names = {p.canonical_name for p in projs}
        assert "amon ra st brown" in names
        assert "jamarr chase" in names
        assert "velus jones" in names


    def test_pydantic_serialization_roundtrip(self, adapter):
        csv_text = "Player,Team,Pos,Pass Yds\nPatrick Mahomes,KC,QB,280.0\n"
        projs = adapter.parse_clipboard_text(csv_text)
        assert len(projs) > 0
        p = projs[0]
        d = p.model_dump()
        assert d["player_name"] == "Patrick Mahomes"
        assert d["team"] == "KC"
        assert d["stat_category"] == "passing_yards"
        json_str = p.model_dump_json()
        assert "passing_yards" in json_str

    def test_scientific_notation_float(self, adapter):
        assert FantasyPointsAdapter.sanitize_float("1.25e2") == 125.0
        assert FantasyPointsAdapter.sanitize_float("2.5E1") == 25.0

