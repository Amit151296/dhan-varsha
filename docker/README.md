# Dhan Varsha - PostgreSQL (Docker)

## Option A: docker-compose (recommended)

Start the database:

    docker-compose up -d

Stop it:

    docker-compose down

Stop it and delete the stored data:

    docker-compose down -v

## Option B: plain docker run

Pull the image:

    docker pull postgres:16

Run the container:

    docker run --name dhanvarsha-postgres -e POSTGRES_USER=dhanvarsha -e POSTGRES_PASSWORD=dhanvarsha123 -e POSTGRES_DB=dhanvarsha -p 5432:5432 -v dhanvarsha_pgdata:/var/lib/postgresql/data -d postgres:16

Stop the container:

    docker stop dhanvarsha-postgres

Start it again later:

    docker start dhanvarsha-postgres

Remove the container (data in the volume is kept):

    docker rm -f dhanvarsha-postgres

## Connection details

- Host: localhost
- Port: 5432
- User: dhanvarsha
- Password: dhanvarsha123
- Database: dhanvarsha
- Connection string: postgresql://dhanvarsha:dhanvarsha123@localhost:5432/dhanvarsha

This matches the `DATABASE_URL` in `backend/.env.example`. Copy that file to `backend/.env` before running the API.
