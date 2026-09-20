from .fluxo import notificacoes_visiveis


def notificacoes(request):
    if not request.user.is_authenticated:
        return {}
    return {'notificacoes_pendentes': notificacoes_visiveis(request.user).filter(lida_em__isnull=True).count()}
