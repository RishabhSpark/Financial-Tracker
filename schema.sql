BEGIN TRANSACTION;
CREATE TABLE drive_files (
	id VARCHAR NOT NULL, 
	name VARCHAR, 
	last_edited DATETIME, 
	PRIMARY KEY (id)
);
INSERT INTO "drive_files" VALUES('1E_uqslKMSykpjzmFqn3EM2enxaB-0zkr','RT Test data-3.pdf','2025-06-11 22:26:03.434000');
INSERT INTO "drive_files" VALUES('1BUrbXO6yQwdb6kWLTwCIXjcX8-iISQAD','RT Test data-2.pdf','2025-06-11 22:25:55.800000');
INSERT INTO "drive_files" VALUES('13_KOi8-KkCD7xG_gWFXelpXn63l2Vvgx','RT Test data-1.pdf','2025-06-10 19:21:07.000000');
CREATE TABLE milestones (
	id INTEGER NOT NULL, 
	po_id VARCHAR, 
	milestone_name VARCHAR, 
	milestone_description VARCHAR, 
	milestone_due_date VARCHAR, 
	milestone_percentage FLOAT, 
	PRIMARY KEY (id), 
	FOREIGN KEY(po_id) REFERENCES purchase_orders (po_id)
);
INSERT INTO "milestones" VALUES(1,'34523','initial',NULL,NULL,20.0);
INSERT INTO "milestones" VALUES(2,'34523','milestone_1',NULL,NULL,40.0);
INSERT INTO "milestones" VALUES(3,'34523','milestone_2',NULL,NULL,40.0);
CREATE TABLE payment_schedule (
	id INTEGER NOT NULL, 
	po_id VARCHAR, 
	payment_date VARCHAR, 
	payment_amount FLOAT, 
	payment_description VARCHAR, 
	PRIMARY KEY (id), 
	FOREIGN KEY(po_id) REFERENCES purchase_orders (po_id)
);
CREATE TABLE purchase_orders (
	id INTEGER NOT NULL, 
	po_id VARCHAR, 
	client_name VARCHAR, 
	amount FLOAT, 
	status VARCHAR, 
	payment_terms INTEGER, 
	payment_type VARCHAR, 
	start_date VARCHAR, 
	end_date VARCHAR, 
	duration_months INTEGER, 
	payment_frequency INTEGER, 
	PRIMARY KEY (id)
);
INSERT INTO "purchase_orders" VALUES(1,'34523','Fiona Inc',80000.0,'Confirmed',30,'milestone','01-04-2025','31-12-2025',NULL,NULL);
INSERT INTO "purchase_orders" VALUES(2,'1234567345','Fiona Inc',80000.0,'Confirmed',60,'periodic','01-06-2025','31-08-2026',NULL,1);
INSERT INTO "purchase_orders" VALUES(3,'1234567890','Papil',87346.0,'Confirmed',90,'periodic','10-04-2024','10-04-2026',24,3);
CREATE UNIQUE INDEX ix_purchase_orders_po_id ON purchase_orders (po_id);
CREATE INDEX ix_purchase_orders_id ON purchase_orders (id);
CREATE INDEX ix_drive_files_name ON drive_files (name);
COMMIT;
