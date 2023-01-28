FROM python:3.10

# Create user
ARG UNAME=demo
ARG UID=1000
ARG GID=1000

RUN groupadd -g ${GID} -o ${UNAME} && \
    useradd -m -u ${UID} -g ${GID} -o -s /bin/bash ${UNAME}


# Switch to the user created
USER ${UNAME}
WORKDIR /home/${UNAME}/service

# Environment variables
ENV PATH="/home/${UNAME}/.local/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Copy requirements
COPY --chown=${UID}:${GID} requirements.txt requirements.txt

RUN pip install --user -r requirements.txt

# Copy service
COPY --chown=${UID}:${GID} main.py .

# demo set as env. embed in code/write to a file
ENV CL_PRODUCT_ID ""
ENV CL_AUTH_TOKEN ""
ENV CL_RSA_PUB_KEY ""


ENV CL_PRODUCT_KEY ""

ENV PORT 8000

CMD python main.py