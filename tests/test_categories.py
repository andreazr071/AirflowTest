import pandas as pd

from datamart_etl.categories import assign_categories, load_rules


def categorize(name, is_merchandise=True):
    frame = pd.DataFrame({"product_code": ["X"], "product_name": [name], "is_merchandise": [is_merchandise]})
    return assign_categories(frame, load_rules()).iloc[0]


def test_keyword_rules_map_to_the_five_categories():
    assert categorize("RED RETROSPOT CHRISTMAS CARDS").category == "Papelería"
    assert categorize("PINK SCARF").category == "Ropa"
    assert categorize("POCKET CALCULATOR").category == "Electrónica"
    assert categorize("SKIPPING ROPE").category == "Deportes"


def test_specific_override_beats_generic_keyword():
    assert categorize("PAPER CHAIN KIT").category == "Hogar"      # no es papelería
    assert categorize("NAPKIN RING GOLD").category == "Hogar"      # no es joyería


def test_no_match_falls_back_to_default_and_says_so():
    row = categorize("GLASS HEART CANDLE POT")
    assert (row.category, row.category_source) == ("Hogar", "default")


def test_non_merchandise_and_unnamed_products():
    assert categorize("POSTAGE", is_merchandise=False).category == "No producto"
    assert categorize(None).category == "Sin clasificar"


def test_keyword_must_be_a_whole_word():
    assert categorize("PENNY FARTHING").category == "Hogar"  # "PEN" no debe disparar con "PENNY"


def test_categoria_de_la_api_tiene_prioridad_sobre_las_reglas():
    import pandas as pd

    from datamart_etl.categories import assign_categories, load_rules

    products = pd.DataFrame({
        "product_code": ["A1", "B2", "C3"],
        "product_name": ["RED NECKLACE", "BLUE MUG", "POSTAGE"],
        "is_merchandise": [True, True, False],
    })
    out = assign_categories(products, load_rules(), {"A1": "Electrónica", "C3": "Deportes"}).set_index("product_code")
    assert out.loc["A1", "category"] == "Electrónica" and out.loc["A1", "category_source"] == "api"
    assert out.loc["B2", "category_source"] == "default"      # sin API ni regla
    assert out.loc["C3", "category"] == "No producto"         # los no-producto no se reclasifican
