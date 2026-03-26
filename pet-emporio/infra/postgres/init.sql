-- Create all 10 service databases
CREATE DATABASE pe_keycloak;
CREATE DATABASE pe_auth;
CREATE DATABASE pe_users;
CREATE DATABASE pe_catalog;
CREATE DATABASE pe_orders;
CREATE DATABASE pe_payments;
CREATE DATABASE pe_bookings;
CREATE DATABASE pe_medical;
CREATE DATABASE pe_notifications;
CREATE DATABASE pe_content;
CREATE DATABASE pe_reports;

-- Create service-specific users (optional but recommended)
CREATE USER auth_user WITH PASSWORD 'auth_pass_dev';
GRANT ALL PRIVILEGES ON DATABASE pe_auth TO auth_user;

CREATE USER user_svc_user WITH PASSWORD 'user_pass_dev';
GRANT ALL PRIVILEGES ON DATABASE pe_users TO user_svc_user;