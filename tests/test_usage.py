def test_nested_and_cyclic_groups():
    from apps.inventory.usage import classify_usage
    result = classify_usage([{'name':'host'},{'name':'spare'}],
        [{'name':'outer','member':[{'name':'inner'}]},
         {'name':'inner','member':[{'name':'outer'},{'name':'host'}]}],
        [{'srcaddr':[{'name':'outer'}], 'dstaddr':[{'name':'host'}]}], complete=True)
    assert result == {'host':'used','spare':'potentially_unused'}


def test_incomplete_and_missing_policy_fields_are_conservative():
    from apps.inventory.usage import classify_usage
    assert classify_usage([{'name':'host'}],[],[],complete=False) == {'host':'unknown'}
    assert classify_usage([{'name':'host'}],[],[{'srcaddr':[{'name':'all'}]}],complete=True) == {'host':'unknown'}


def test_all_and_negated_policy_references_do_not_hide_unused_resources():
    from apps.inventory.usage import classify_usage
    result=classify_usage([{'name':'all'},{'name':'host'},{'name':'spare'}],
        [{'name':'used_group','member':[{'name':'host'}]},{'name':'spare_group','member':[]}],
        [{'srcaddr':[{'name':'all'}],'dstaddr':[{'name':'used_group'}],'dstaddr-negate':'enable'}],
        complete=True,include_groups=True)
    assert result=={'all':'used','host':'used','spare':'potentially_unused','spare_group':'potentially_unused','used_group':'used'}
    assert classify_usage([{'name':'spare'}],[],[{'srcaddr':[{'name':'all'}],'dstaddr':[]}],complete=True)=={'spare':'potentially_unused'}
