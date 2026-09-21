from .fluxo import notificacoes_visiveis


def notificacoes(requisicao):
    if not requisicao.user.is_authenticated:
        return {}
    return {'notificacoes_pendentes': notificacoes_visiveis(requisicao.user).filter(lida_em__isnull=True).count()}
