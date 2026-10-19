import pytest
from evals.harness import asks_user


@pytest.mark.parametrize(
    ("answer", "asks"),
    [
        ("¿Cuántos ml tenía cada caña?", True),
        ("Dime la cantidad que prefieras y te las registro.", True),  # conv-10, 18 Oct: no question mark
        ("Necesito saber cuántos gramos fueron.", True),
        ("Me indicas el aceite que usaste y lo apunto.", True),
        ("He registrado las dos cañas de cerveza (400 ml).", False),
        ("Te indico lo que dicen las guías.", False),
        ("Registrado: 1 manzana (168 g). Si el tamaño era diferente, dímelo y lo ajustamos.", False),  # conv-14
    ],
)
def test_the_simulated_user_answers_questions_and_requests(answer, asks):
    assert asks_user(answer) is asks
