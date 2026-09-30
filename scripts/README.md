# Scripts

Scripts são entrypoints operacionais; a implementação de domínio permanece em
`src/sod_platform`.

- `runtime/`: materializações V2 (Context/HTS, baseline, expected access,
  evidence, policy, risk e Gold).
- `validation/`: mart e diagnósticos offline; não são dependência do runtime.
- `operations/`: gates, registro de execução e reset local.
- `audit/`: auditorias somente leitura.
- `maintenance/`: validações e benchmarks locais.
- `development/`: geração de dados, demonstrações e execução de notebooks.

Não há entrypoints na raiz de `scripts/`. Automações devem usar os caminhos por
responsabilidade acima.
