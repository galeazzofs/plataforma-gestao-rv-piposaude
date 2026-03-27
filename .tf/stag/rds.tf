resource "aws_db_instance" "comissoes_stag" {
  identifier     = "comissoes-stag"
  engine         = "postgres"
  engine_version = "16.4"
  instance_class = "db.t3.micro"

  allocated_storage     = 20
  max_allocated_storage = 50

  db_name  = "comissoes_stag"
  username = "comissoes_admin"
  password = var.db_password

  multi_az                = false
  backup_retention_period = 7
  skip_final_snapshot     = true

  tags = {
    Squad       = "RevOps"
    Domain      = "Comissoes"
    Environment = "stag"
  }
}
