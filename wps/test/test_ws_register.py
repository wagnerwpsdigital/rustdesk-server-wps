"""Teste de protocolo do fork wps/ws-register do hbbs 1.1.16.

Sobe contra um hbbs local (porta WS = -p + 2) e verifica:
  T1 RegisterPk por WS -> RegisterPkResponse OK com keep_alive > 0, socket aberto
  T2 heartbeat vazio do servidor chega em < 15 s (e o eco do cliente é aceito)
  T3 OnlineRequest de outra conexão (mesmo IP público) vê o host online
  T4 PunchHoleRequest de outra conexão (mesmo IP público) chega ao host pelo
     stream registrado como PunchHole com nat_type SYMMETRIC (relay forçado)
  T5 RequestRelay chega ao host pelo stream registrado
  T6 host desconecta -> OnlineRequest mostra offline na hora
  T7 PunchHoleRequest para id inexistente -> ID_NOT_EXIST (regressão)
Uso: python test_ws_register.py <ws_url> <chave_publica>
"""
import asyncio
import os
import sys

import websockets

import rendezvous_pb2 as pb

URL = sys.argv[1] if len(sys.argv) > 1 else "ws://127.0.0.1:31118"
# chave pública do servidor (hbbs exige por padrão: -k - => key = pk)
KEY = sys.argv[2] if len(sys.argv) > 2 else ""
PUB_IP = {"X-Real-IP": "203.0.113.5"}
HOST_ID = "917010272"
# fixos: o hbbs grava uuid/pk no db e recusa (UUID_MISMATCH) outro uuid para o mesmo id
HOST_UUID = b"wps-ensaio-uuid1"
HOST_PK = bytes(range(32))
results = []


def check(name, ok, detail=""):
    results.append((name, ok))
    print(("PASS " if ok else "FAIL ") + name + (" — " + detail if detail else ""))


def msg(**kw):
    m = pb.RendezvousMessage()
    for k, v in kw.items():
        getattr(m, k).CopyFrom(v)
    return m.SerializeToString()


async def recv_msg(ws, timeout, skip_empty=True):
    """Próxima mensagem não vazia (ecoa vazios como o cliente 1.5.0)."""
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while True:
        data = await asyncio.wait_for(ws.recv(), max(0.01, end - loop.time()))
        if not data and skip_empty:
            await ws.send(b"")
            continue
        m = pb.RendezvousMessage()
        m.ParseFromString(data)
        return m, data


async def connect():
    return await websockets.connect(URL, additional_headers=PUB_IP, open_timeout=5)


async def online(ws_id):
    ws = await connect()
    await ws.send(msg(online_request=pb.OnlineRequest(id=ws_id, peers=[HOST_ID])))
    m, _ = await recv_msg(ws, 5)
    await ws.close()
    return m.WhichOneof("union") == "online_response" and bool(m.online_response.states[0] & 0x80)


async def main():
    host = await connect()
    await host.send(msg(register_pk=pb.RegisterPk(
        id=HOST_ID, uuid=HOST_UUID, pk=HOST_PK)))
    m, _ = await recv_msg(host, 5)
    rpr = m.register_pk_response
    check("T1 RegisterPk WS -> OK + keep_alive",
          m.WhichOneof("union") == "register_pk_response"
          and rpr.result == pb.RegisterPkResponse.OK and rpr.keep_alive > 0,
          f"result={rpr.result} keep_alive={rpr.keep_alive}")

    t0 = asyncio.get_running_loop().time()
    try:
        data = await asyncio.wait_for(host.recv(), 15)
        dt = asyncio.get_running_loop().time() - t0
        await host.send(b"")
        check("T2 heartbeat vazio em 5-15 s", data == b"" and 5 <= dt <= 15,
              f"{dt:.1f}s len={len(data)}")
    except asyncio.TimeoutError:
        check("T2 heartbeat vazio < 15 s", False, "timeout")

    check("T3 OnlineRequest vê host online", await online("web-ctl-1"))

    # T8: só heartbeat+eco por 40 s (> 30 s de timeout de leitura do hbbs e > REG_TIMEOUT)
    beats = 0
    loop = asyncio.get_running_loop()
    end = loop.time() + 40
    try:
        while loop.time() < end:
            data = await asyncio.wait_for(host.recv(), 15)
            if data == b"":
                beats += 1
                await host.send(b"")
        alive = await online("web-ctl-3")
        check("T8 stream vivo 40 s só com heartbeat", alive and beats >= 3, f"beats={beats}")
    except Exception as e:
        check("T8 stream vivo 40 s só com heartbeat", False, repr(e))

    ctl = await connect()
    await ctl.send(msg(punch_hole_request=pb.PunchHoleRequest(
        id=HOST_ID, nat_type=pb.ASYMMETRIC, licence_key=KEY)))
    try:
        m, _ = await recv_msg(host, 5)
        ok = m.WhichOneof("union") == "punch_hole" and m.punch_hole.nat_type == pb.SYMMETRIC
        check("T4 PunchHole pelo stream, relay forçado", ok,
              f"{m.WhichOneof('union')} nat={m.punch_hole.nat_type} relay={m.punch_hole.relay_server!r}")
    except asyncio.TimeoutError:
        check("T4 PunchHole pelo stream, relay forçado", False, "timeout")
    await ctl.close()

    ctl = await connect()
    await ctl.send(msg(request_relay=pb.RequestRelay(id=HOST_ID, uuid="u-test")))
    try:
        m, _ = await recv_msg(host, 5)
        check("T5 RequestRelay pelo stream", m.WhichOneof("union") == "request_relay",
              str(m.WhichOneof("union")))
    except asyncio.TimeoutError:
        check("T5 RequestRelay pelo stream", False, "timeout")
    await ctl.close()

    await host.close()
    await asyncio.sleep(0.5)
    check("T6 desconexão -> offline imediato", not await online("web-ctl-2"))

    ctl = await connect()
    await ctl.send(msg(punch_hole_request=pb.PunchHoleRequest(id="000000000", licence_key=KEY)))
    m, _ = await recv_msg(ctl, 5)
    check("T7 id inexistente -> ID_NOT_EXIST",
          m.WhichOneof("union") == "punch_hole_response"
          and m.punch_hole_response.failure == pb.PunchHoleResponse.ID_NOT_EXIST)
    await ctl.close()

    failed = [n for n, ok in results if not ok]
    print(f"\n{len(results) - len(failed)}/{len(results)} PASS")
    sys.exit(1 if failed else 0)


asyncio.run(main())
