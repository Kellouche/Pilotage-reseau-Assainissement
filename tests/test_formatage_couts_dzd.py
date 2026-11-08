import pytest
from src.domain.agents_expertise import formater_cout_dzd, formater_nombre_fr

def test_formater_cout_dzd_standard():
    # Test avec entiers et flottants
    assert formater_cout_dzd(1446816) == "1 446 816,00 DZD"
    assert formater_cout_dzd(1446816.5) == "1 446 816,50 DZD"
    assert formater_cout_dzd(330964500) == "330 964 500,00 DZD"
    assert formater_cout_dzd(0) == "0,00 DZD"
    assert formater_cout_dzd(None) == "0,00 DZD"

    # Test sans décimales
    assert formater_cout_dzd(1446816, avec_decimales=False) == "1 446 816 DZD"

    # Test sans unité
    assert formater_cout_dzd(1446816, inclure_unite=False) == "1 446 816,00"

def test_formater_nombre_fr():
    assert formater_nombre_fr(1.716, 3) == "1,716"
    assert formater_nombre_fr(98.9, 1) == "98,9"
    assert formater_nombre_fr(0.019, 3) == "0,019"
    assert formater_nombre_fr(100.0, 1) == "100,0"
    assert formater_nombre_fr(0.0, 3) == "0,000"
