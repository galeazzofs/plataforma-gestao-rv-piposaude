resource "aws_db_instance" "comissoes_prod" {
  identifier     = "comissoes-prod"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = "db.t3.small"

  allocated_storage     = 30
  max_allocated_storage = 100

  db_name  = "comissoes_prod"
  username = "comissoes_admin"
  password = var.db_password

  multi_az                = true
  backup_retention_period = 30
  skip_final_snapshot     = false
  final_snapshot_identifier = "comissoes-prod-final-snapshot"

  deletion_protection = true

  tags = {
    Squad       = "RevOps"
    Domain      = "Comissoes"
    Environment = "prod"
  }
}
