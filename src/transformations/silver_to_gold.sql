-- silver -> gold: KPIs operativos y comerciales por fecha de despacho y ruta.
-- Entrada: vista silver_envios. Excluye envíos CANCELADO.
-- Salida: columnas y tipos del contrato src/contracts/gold_desempeno_rutas.json.
select
    fecha_despacho,
    origen,
    destino,
    count(*)                                                    as envios_total,
    count_if(estado = 'ENTREGADO')                              as envios_entregados,
    count_if(estado = 'ENTREGADO'
             and fecha_entrega <= fecha_entrega_prometida)      as envios_a_tiempo,
    cast(
        100.0 * count_if(estado = 'ENTREGADO'
                         and fecha_entrega <= fecha_entrega_prometida)
        / nullif(count_if(estado = 'ENTREGADO'), 0)
        as decimal(5, 2))                                       as otd_pct,
    cast(
        avg(case when estado = 'ENTREGADO'
                 then datediff(fecha_entrega, fecha_despacho) end)
        as decimal(6, 2))                                       as dias_transito_prom,
    cast(sum(peso_kg) as decimal(14, 2))                        as peso_total_kg,
    cast(sum(tarifa_pen) as decimal(14, 2))                     as ingreso_total_pen,
    cast(sum(tarifa_pen) / nullif(sum(peso_kg), 0)
         as decimal(10, 4))                                     as ingreso_por_kg_pen
from silver_envios
where estado <> 'CANCELADO'
group by fecha_despacho, origen, destino
