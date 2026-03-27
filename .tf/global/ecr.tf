resource "aws_ecr_repository" "backend" {
  name                 = "plataforma-comissoes-backend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Squad   = "RevOps"
    Domain  = "Comissoes"
    Service = "plataforma-comissoes"
  }
}

resource "aws_ecr_repository" "frontend" {
  name                 = "plataforma-comissoes-frontend"
  image_tag_mutability = "MUTABLE"

  image_scanning_configuration {
    scan_on_push = true
  }

  tags = {
    Squad   = "RevOps"
    Domain  = "Comissoes"
    Service = "plataforma-comissoes"
  }
}
