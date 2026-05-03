-- Tabla: Inversiones (AgenteFinanciero)
create table if not exists "Inversiones" (
    id            bigserial primary key,
    simbolo       text        not null,
    rendimiento_pct   numeric(8, 2),
    volatilidad_pct   numeric(8, 2),
    rsi               numeric(5, 1),
    senal             text,
    analisis          text,
    created_at    timestamptz not null default now()
);

-- Tabla: Contenido (AgenteContenido)
create table if not exists "Contenido" (
    id                bigserial primary key,
    plataforma        text        not null,
    categoria         text        not null,
    tema              text,
    formato           text,
    alcance_estimado  integer,
    engagement_pct    numeric(5, 1),
    brief             text,
    created_at        timestamptz not null default now()
);

-- Tabla: noticias (AgenteTuristico)
create table if not exists "noticias" (
    id              bigserial primary key,
    destino         text        not null,
    presupuesto     text        not null,
    dias            integer,
    costo_diario_usd integer,
    mejor_epoca     text,
    recomendacion   text,
    created_at      timestamptz not null default now()
);
