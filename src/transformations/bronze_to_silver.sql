-- bronze -> silver: un registro por envío único y válido, tipado y normalizado.
-- Entrada: vista bronze_envios (CSV crudo, todas las columnas como string).
-- Salida: columnas y tipos del contrato src/contracts/silver_envios.json.
with limpio as (
    select
        trim(envio_id)                                      as envio_id,
        trim(cliente_id)                                    as cliente_id,
        to_date(trim(fecha_despacho))                       as fecha_despacho,
        to_date(trim(fecha_entrega_prometida))              as fecha_entrega_prometida,
        to_date(nullif(trim(fecha_entrega), ''))            as fecha_entrega,
        initcap(trim(origen))                               as origen,
        initcap(trim(destino))                              as destino,
        upper(trim(tipo_carga))                             as tipo_carga,
        cast(peso_kg as decimal(10, 2))                     as peso_kg,
        cast(tarifa_pen as decimal(12, 2))                  as tarifa_pen,
        upper(trim(estado))                                 as estado,
        row_number() over (
            partition by trim(envio_id)
            order by fecha_despacho
        )                                                   as rn
    from bronze_envios
    where envio_id is not null
      and trim(envio_id) <> ''
)
select
    envio_id,
    cliente_id,
    fecha_despacho,
    fecha_entrega_prometida,
    fecha_entrega,
    origen,
    destino,
    tipo_carga,
    peso_kg,
    tarifa_pen,
    estado
from limpio
where rn = 1
