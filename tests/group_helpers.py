from apps.firewalls.models import FirewallGroup, FirewallGroupMember


def group_for(vdom):
    group,_=FirewallGroup.objects.get_or_create(name=f'Fixture {vdom.pk}')
    FirewallGroupMember.objects.get_or_create(group=group,firewall=vdom.firewall,defaults={'vdom':vdom})
    return group
