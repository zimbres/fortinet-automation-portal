def classify_usage(addresses, groups, policies, *, complete: bool, include_groups=False):
    names = {x['name'] for x in addresses}
    group_map = {x['name']:x.get('member',[]) for x in groups}
    used, visited = set(), set()
    uncertain = not complete

    def visit(name):
        nonlocal uncertain
        if name == 'all':
            # A reference to the built-in wildcard does not reference every
            # separately named object that happens to match its traffic.
            if name in names: used.add(name)
            return
        if name in visited:
            return
        visited.add(name)
        if name in names:
            used.add(name)
        elif name in group_map:
            used.add(name)
            if not isinstance(group_map[name],list):
                uncertain = True
                return
            for member in group_map[name]:
                if not isinstance(member, dict) or 'name' not in member:
                    uncertain = True
                else:
                    visit(member['name'])
        else:
            uncertain = True

    for policy in policies:
        for field in ['srcaddr','dstaddr']:
            refs = policy.get(field)
            if not isinstance(refs, list):
                uncertain = True
                continue
            for ref in refs:
                if isinstance(ref, dict) and 'name' in ref:
                    visit(ref['name'])
                else:
                    uncertain = True
    return {name:'used' if name in used else 'unknown' if uncertain else 'potentially_unused' for name in sorted(names | set(group_map) if include_groups else names)}
