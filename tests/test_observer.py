from global_hybrid_v2.observer.witness import ReadOnlyWitness


def test_witness_has_no_mutation_api():
    witness = ReadOnlyWitness()
    forbidden = {"write", "mutate", "execute", "promote", "update_authority", "tool"}
    assert not forbidden.intersection(set(dir(witness)))
