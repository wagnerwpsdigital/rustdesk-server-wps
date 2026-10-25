# WPS fork do rustdesk-server 1.1.16 — registro por TCP/WebSocket

Fork AGPL-3.0 de `rustdesk/rustdesk-server` tag 1.1.16 (73523b3). Só o `hbbs` muda; `hbbr` é o oficial.

## Problema
O hbbs OSS responde `NOT_SUPPORT` a `RegisterPk` recebido por TCP/WebSocket e fecha o socket
(recurso do Server Pro). Um host que só alcança a porta 443 (WebSocket via Cloudflare) nunca fica
online — o cliente loga `unknown RegisterPkResponse`.

## Mudança (`src/rendezvous_server.rs`, marcada com `WPS fork`)
- `RegisterPk` por TCP/WS: mesma validação do UDP (`check_register_pk`), resposta `OK` com
  `keep_alive = 30`, stream fica aberto e vira canal (`Sink::Chan`) de um writer task.
- Writer task: heartbeat vazio a cada 10 s (o cliente 1.5.x ecoa); eco/tráfego renova `last_reg_time`.
- `reg_peers` (addr da conexão → id, canal): `PunchHole`/`RequestRelay`/`FetchLocalAddr` para esse
  peer vão pelo stream (`send_to_peer`), com relay forçado (`nat_type = SYMMETRIC`, sem intranet).
- Endereço do peer WS = IP de `X-Real-IP`/1º de `X-Forwarded-For` + porta de origem da conexão do
  proxy (upstream usava porta 0 → colisão entre peers atrás do mesmo IP público).
  **Confiável só porque a porta WS (21118) não é publicada — só o proxy alcança.**
- `OnlineRequest` também respondido no stream; desconexão marca o peer offline na hora.
- Comando admin `ws-peers` (`wp`) na porta 21115 de loopback.

## Teste
`wps/test/run_test.sh` (precisa de `websockets` + `protobuf` e `rendezvous_pb2.py` gerado por
`protoc --python_out` de `libs/hbb_common/protos/rendezvous.proto`): sobe um hbbs descartável e
verifica T1–T8 (registro, heartbeat, online, stream vivo 40 s, PunchHole/RequestRelay pelo stream,
offline ao desconectar, regressão ID_NOT_EXIST).

## Build para a Friday (x86_64, estático)

`bash wps/build-musl.sh` num Mac com `rustup`, `zig` e `cargo-zigbuild`. Saída:
`target/x86_64-unknown-linux-musl/release/hbbs` (ELF estático). O ensaio confere o sha256.
Build de 25/10/2026: sha256 `dade0eb90f9b430fa27cbe0c4166ab657ae3eac471b4fb99a7dae4c20c1ccb6c`,
8/8 no `wps/test` rodando na própria Friday.
