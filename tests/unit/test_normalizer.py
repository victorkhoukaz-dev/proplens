"""
Unit tests for app.core.normalizer: PlayerNameNormalizer and TeamNormalizer.
Verifies 5-step name normalization, 25+ nickname aliases, RapidFuzz matching with guardrails,
and all 32 canonical NFL team mappings and abbreviations.
"""

import pytest

from app.core.normalizer import (
    NFL_CANONICAL_TEAMS,
    NFL_TEAM_LOOKUP,
    PlayerNameNormalizer,
    TeamNormalizer,
)


class TestPlayerNameNormalizer:
    """Test suite for PlayerNameNormalizer."""

    def test_clean_name_empty_or_none(self):
        assert PlayerNameNormalizer.clean_name("") == ""
        assert PlayerNameNormalizer.clean_name(None) == ""
        assert PlayerNameNormalizer.clean_name("   ") == ""

    def test_suffix_stripping(self):
        assert PlayerNameNormalizer.clean_name("Patrick Mahomes II") == "patrick mahomes"
        assert PlayerNameNormalizer.clean_name("Kenneth Walker III") == "kenneth walker"
        assert PlayerNameNormalizer.clean_name("Marvin Harrison Jr.") == "marvin harrison"
        assert PlayerNameNormalizer.clean_name("Travis Etienne Jr.") == "travis etienne"
        assert PlayerNameNormalizer.clean_name("Robert Griffin III") == "robert griffin"
        assert PlayerNameNormalizer.clean_name("John Smith Sr.") == "john smith"
        assert PlayerNameNormalizer.clean_name("Tyrone Tracy Jr") == "tyrone tracy"

    def test_inverted_names(self):
        assert PlayerNameNormalizer.clean_name("Mahomes, Patrick") == "patrick mahomes"
        assert PlayerNameNormalizer.clean_name("Walker III, Kenneth") == "kenneth walker"
        assert PlayerNameNormalizer.clean_name("Harrison, Marvin, Jr.") == "marvin harrison"
        assert PlayerNameNormalizer.clean_name("Allen, Josh") == "joshua allen"

    def test_punctuation_and_spaced_initials(self):
        assert PlayerNameNormalizer.clean_name("Ja'Marr Chase") == "jamarr chase"
        assert PlayerNameNormalizer.clean_name("De'Von Achane") == "devon achane"
        assert PlayerNameNormalizer.clean_name("A.J. Brown") == "aj brown"
        assert PlayerNameNormalizer.clean_name("A. J. Brown") == "aj brown"
        assert PlayerNameNormalizer.clean_name("C.J. Stroud") == "cj stroud"
        assert PlayerNameNormalizer.clean_name("D.J. Moore") == "dj moore"
        assert PlayerNameNormalizer.clean_name("T.J. Hockenson") == "tj hockenson"
        assert PlayerNameNormalizer.clean_name("J.K. Dobbins") == "jk dobbins"
        assert PlayerNameNormalizer.clean_name("Amon-Ra St. Brown") == "amon ra st brown"
        assert PlayerNameNormalizer.clean_name("Marquez Valdes-Scantling") == "marquez valdes scantling"
        assert PlayerNameNormalizer.clean_name("Tre'Quan Smith") == "trequan smith"

    def test_nickname_and_alias_mapping_25_plus(self):
        # Full aliases
        assert PlayerNameNormalizer.clean_name("Hollywood Brown") == "marquise brown"
        assert PlayerNameNormalizer.clean_name("Chig Okonkwo") == "chigoziem okonkwo"
        assert PlayerNameNormalizer.clean_name("Tank Dell") == "nathaniel dell"
        assert PlayerNameNormalizer.clean_name("Robbie Anderson") == "chosen anderson"
        assert PlayerNameNormalizer.clean_name("Robby Anderson") == "chosen anderson"
        assert PlayerNameNormalizer.clean_name("Robbie Chosen") == "chosen anderson"
        assert PlayerNameNormalizer.clean_name("PJ Walker") == "phillip walker"
        assert PlayerNameNormalizer.clean_name("Ray-Ray McCloud") == "rayray mccloud"
        assert PlayerNameNormalizer.clean_name("CeeDee Lamb") == "ceedee lamb"
        assert PlayerNameNormalizer.clean_name("D'Andre Swift") == "dandre swift"
        assert PlayerNameNormalizer.clean_name("Scotty Miller") == "scott miller"
        assert PlayerNameNormalizer.clean_name("Jeff Wilson") == "jeffery wilson"

        # Diminutives / Casual First Names
        assert PlayerNameNormalizer.clean_name("Gabe Davis") == "gabriel davis"
        assert PlayerNameNormalizer.clean_name("Gabriel Davis") == "gabriel davis"
        assert PlayerNameNormalizer.clean_name("Mitch Trubisky") == "mitchell trubisky"
        assert PlayerNameNormalizer.clean_name("Mitchell Trubisky") == "mitchell trubisky"
        assert PlayerNameNormalizer.clean_name("Josh Allen") == "joshua allen"
        assert PlayerNameNormalizer.clean_name("Joshua Allen") == "joshua allen"
        assert PlayerNameNormalizer.clean_name("Cam Akers") == "cameron akers"
        assert PlayerNameNormalizer.clean_name("Cameron Akers") == "cameron akers"
        assert PlayerNameNormalizer.clean_name("Pat Mahomes") == "patrick mahomes"
        assert PlayerNameNormalizer.clean_name("Patrick Mahomes") == "patrick mahomes"
        assert PlayerNameNormalizer.clean_name("Ken Walker") == "kenneth walker"
        assert PlayerNameNormalizer.clean_name("Kenneth Walker") == "kenneth walker"
        assert PlayerNameNormalizer.clean_name("Dan Jones") == "daniel jones"
        assert PlayerNameNormalizer.clean_name("Danny Jones") == "daniel jones"
        assert PlayerNameNormalizer.clean_name("Mike Pittman") == "michael pittman"
        assert PlayerNameNormalizer.clean_name("Tony Pollard") == "anthony pollard"
        assert PlayerNameNormalizer.clean_name("Alex Mattison") == "alexander mattison"
        assert PlayerNameNormalizer.clean_name("Zach Ertz") == "zachary ertz"
        assert PlayerNameNormalizer.clean_name("Nick Chubb") == "nicholas chubb"
        assert PlayerNameNormalizer.clean_name("Nate Dell") == "nathaniel dell"
        assert PlayerNameNormalizer.clean_name("Ben Roethlisberger") == "benjamin roethlisberger"
        assert PlayerNameNormalizer.clean_name("Sam Darnold") == "samuel darnold"
        assert PlayerNameNormalizer.clean_name("Chris Godwin") == "christopher godwin"
        assert PlayerNameNormalizer.clean_name("Rob Gronkowski") == "robert gronkowski"
        assert PlayerNameNormalizer.clean_name("Tom Brady") == "thomas brady"

    def test_match_player_exact_and_fuzzy(self):
        pool = [
            "Patrick Mahomes",
            "Gabriel Davis",
            "Travis Kelce",
            "Marquise Brown",
            "Kenneth Walker III",
            "Ja'Marr Chase",
        ]

        # Exact match
        assert PlayerNameNormalizer.match_player("Patrick Mahomes", pool) == "Patrick Mahomes"
        # Suffix variation
        assert PlayerNameNormalizer.match_player("Patrick Mahomes II", pool) == "Patrick Mahomes"
        # Inversion
        assert PlayerNameNormalizer.match_player("Mahomes, Patrick", pool) == "Patrick Mahomes"
        # Nickname
        assert PlayerNameNormalizer.match_player("Gabe Davis", pool) == "Gabriel Davis"
        assert PlayerNameNormalizer.match_player("Hollywood Brown", pool) == "Marquise Brown"
        assert PlayerNameNormalizer.match_player("Ken Walker", pool) == "Kenneth Walker III"
        assert PlayerNameNormalizer.match_player("Jamar Chase", pool) == "Ja'Marr Chase"

        # Non matching
        assert PlayerNameNormalizer.match_player("Aaron Rodgers", pool) is None
        assert PlayerNameNormalizer.match_player("", pool) is None
        assert PlayerNameNormalizer.match_player("Patrick Mahomes", []) is None

    def test_match_player_with_guardrails(self):
        candidate_pool = ["Josh Allen (QB)", "Josh Allen (EDGE)"]
        candidate_metadata = {
            "Josh Allen (QB)": {"team": "BUF", "position": "QB"},
            "Josh Allen (EDGE)": {"team": "JAX", "position": "EDGE"},
        }

        match_qb = PlayerNameNormalizer.match_player(
            "Josh Allen",
            candidate_pool,
            position="QB",
            team="BUF",
            candidate_metadata=candidate_metadata,
        )
        assert match_qb == "Josh Allen (QB)"

        match_edge = PlayerNameNormalizer.match_player(
            "Josh Allen",
            candidate_pool,
            position="EDGE",
            team="JAX",
            candidate_metadata=candidate_metadata,
        )
        assert match_edge == "Josh Allen (EDGE)"


class TestTeamNormalizer:
    """Test suite for TeamNormalizer."""

    def test_all_32_canonical_teams_exist(self):
        assert len(NFL_CANONICAL_TEAMS) == 32
        expected_teams = {
            "ARI", "ATL", "BAL", "BUF", "CAR", "CHI", "CIN", "CLE",
            "DAL", "DEN", "DET", "GB", "HOU", "IND", "JAX", "KC",
            "LAC", "LAR", "LV", "MIA", "MIN", "NE", "NO", "NYG",
            "NYJ", "PHI", "PIT", "SEA", "SF", "TB", "TEN", "WAS"
        }
        assert NFL_CANONICAL_TEAMS == expected_teams

    def test_canonical_team_pass_through(self):
        for team in NFL_CANONICAL_TEAMS:
            assert TeamNormalizer.canonical_team(team) == team
            assert TeamNormalizer.canonical_team(team.lower()) == team

    def test_team_abbreviation_variants(self):
        # Kansas City
        assert TeamNormalizer.canonical_team("KAN") == "KC"
        assert TeamNormalizer.canonical_team("KCC") == "KC"
        assert TeamNormalizer.canonical_team("Kansas City") == "KC"
        assert TeamNormalizer.canonical_team("Kansas City Chiefs") == "KC"
        assert TeamNormalizer.canonical_team("Chiefs") == "KC"

        # Washington
        assert TeamNormalizer.canonical_team("WSH") == "WAS"
        assert TeamNormalizer.canonical_team("WFT") == "WAS"
        assert TeamNormalizer.canonical_team("Washington") == "WAS"
        assert TeamNormalizer.canonical_team("Washington Commanders") == "WAS"
        assert TeamNormalizer.canonical_team("Washington Football Team") == "WAS"
        assert TeamNormalizer.canonical_team("Redskins") == "WAS"

        # Las Vegas / Oakland
        assert TeamNormalizer.canonical_team("LVR") == "LV"
        assert TeamNormalizer.canonical_team("OAK") == "LV"
        assert TeamNormalizer.canonical_team("Las Vegas Raiders") == "LV"
        assert TeamNormalizer.canonical_team("Oakland Raiders") == "LV"

        # Tampa Bay
        assert TeamNormalizer.canonical_team("TAM") == "TB"
        assert TeamNormalizer.canonical_team("TBB") == "TB"
        assert TeamNormalizer.canonical_team("Tampa Bay") == "TB"
        assert TeamNormalizer.canonical_team("Tampa Bay Buccaneers") == "TB"
        assert TeamNormalizer.canonical_team("Bucs") == "TB"

        # New Orleans
        assert TeamNormalizer.canonical_team("NOR") == "NO"
        assert TeamNormalizer.canonical_team("NOS") == "NO"
        assert TeamNormalizer.canonical_team("New Orleans") == "NO"
        assert TeamNormalizer.canonical_team("New Orleans Saints") == "NO"
        assert TeamNormalizer.canonical_team("NOLA") == "NO"

        # San Francisco
        assert TeamNormalizer.canonical_team("SFO") == "SF"
        assert TeamNormalizer.canonical_team("San Francisco") == "SF"
        assert TeamNormalizer.canonical_team("San Francisco 49ers") == "SF"
        assert TeamNormalizer.canonical_team("49ers") == "SF"
        assert TeamNormalizer.canonical_team("Niners") == "SF"

        # Green Bay
        assert TeamNormalizer.canonical_team("GNB") == "GB"
        assert TeamNormalizer.canonical_team("GBP") == "GB"
        assert TeamNormalizer.canonical_team("Green Bay Packers") == "GB"
        assert TeamNormalizer.canonical_team("Packers") == "GB"

        # New England
        assert TeamNormalizer.canonical_team("NWE") == "NE"
        assert TeamNormalizer.canonical_team("NEP") == "NE"
        assert TeamNormalizer.canonical_team("New England") == "NE"
        assert TeamNormalizer.canonical_team("New England Patriots") == "NE"
        assert TeamNormalizer.canonical_team("Patriots") == "NE"
        assert TeamNormalizer.canonical_team("Boston") == "NE"

        # Los Angeles Chargers & Rams / San Diego & St. Louis
        assert TeamNormalizer.canonical_team("SD") == "LAC"
        assert TeamNormalizer.canonical_team("SDC") == "LAC"
        assert TeamNormalizer.canonical_team("Los Angeles Chargers") == "LAC"
        assert TeamNormalizer.canonical_team("LA Chargers") == "LAC"
        assert TeamNormalizer.canonical_team("San Diego Chargers") == "LAC"
        assert TeamNormalizer.canonical_team("LAR") == "LAR"
        assert TeamNormalizer.canonical_team("STL") == "LAR"
        assert TeamNormalizer.canonical_team("Los Angeles Rams") == "LAR"
        assert TeamNormalizer.canonical_team("St. Louis Rams") == "LAR"

        # Arizona / Phoenix
        assert TeamNormalizer.canonical_team("ARZ") == "ARI"
        assert TeamNormalizer.canonical_team("PHO") == "ARI"
        assert TeamNormalizer.canonical_team("Arizona Cardinals") == "ARI"
        assert TeamNormalizer.canonical_team("Phoenix Cardinals") == "ARI"

        # Jacksonville / Tennessee / Houston / Indianapolis / etc.
        assert TeamNormalizer.canonical_team("JAC") == "JAX"
        assert TeamNormalizer.canonical_team("JAG") == "JAX"
        assert TeamNormalizer.canonical_team("Tennessee Titans") == "TEN"
        assert TeamNormalizer.canonical_team("Tennessee Oilers") == "TEN"
        assert TeamNormalizer.canonical_team("Houston Texans") == "HOU"
        assert TeamNormalizer.canonical_team("Indy") == "IND"
        assert TeamNormalizer.canonical_team("Philly") == "PHI"
        assert TeamNormalizer.canonical_team("Cincy") == "CIN"
        assert TeamNormalizer.canonical_team("Pitt") == "PIT"

    def test_canonical_team_empty_or_none(self):
        assert TeamNormalizer.canonical_team("") == ""
        assert TeamNormalizer.canonical_team(None) == ""
        assert TeamNormalizer.canonical_team("   ") == ""
