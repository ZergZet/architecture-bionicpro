CREATE TABLE IF NOT EXISTS clients (
    id                 SERIAL PRIMARY KEY,
    full_name          VARCHAR(200) NOT NULL,
    email              VARCHAR(200) NOT NULL UNIQUE,
    username           VARCHAR(100) NOT NULL UNIQUE,
    prosthesis_type    VARCHAR(50)  NOT NULL,
    prosthesis_model   VARCHAR(100) NOT NULL,
    serial_number      VARCHAR(50)  NOT NULL UNIQUE,
    order_number       VARCHAR(50)  NOT NULL,
    order_price        NUMERIC(12,2) NOT NULL,
    install_date       DATE          NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_clients_serial  ON clients(serial_number);
CREATE INDEX IF NOT EXISTS idx_clients_install ON clients(install_date);