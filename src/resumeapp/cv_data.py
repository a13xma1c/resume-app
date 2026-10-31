"""Structured CV data for Alex Maican."""

CV_DATA = {
    "personal": {
        "name": "Alex Maican",
        "title": "Big Data Engineer",
        "location": "Bucharest, Romania",
        "email": "test@test.com",
        "phone": "+0000000000",
        "linkedin": "https://www.linkedin.com/in/alex-maican-7b6172b8",
        "linkedin_display": "linkedin.com/in/alex-maican-7b6172b8",
        "summary": (
            "I am a Big Data Engineer at IBM with over 7 years of experience building scalable "
            "data platforms and batch and real-time data pipelines. My expertise includes Python, "
            "SQL, Apache Spark, Scala, Apache Airflow, and cloud data platforms such as Google Cloud Platform "
            "and AWS. I have hands-on experience with data lake and warehouse architectures, distributed "
            "processing, streaming technologies, workflow orchestration, and CI/CD practices. Throughout my "
            "career at IBM, eMAG, and Orange Services, I have developed reliable data solutions, optimized "
            "processing performance, automated workflows, and supported analytics through high-quality, "
            "well-governed datasets. I enjoy solving complex technical challenges and building efficient, "
            "maintainable data infrastructure that delivers business value."
        ),
        "highlights": [
            {"label": "Experience", "value": "7+ Years", "desc": "Big Data & Cloud Pipelines"},
            {"label": "Scale", "value": "1B+ Rows/Day", "desc": "Stream & Batch Processing"},
            {"label": "Cloud & Lakehouse", "value": "GCP • AWS • Snowflake", "desc": "Modern Data Architecture"},
            {"label": "Orchestration & DevOps", "value": "Airflow • K8s • Terraform", "desc": "End-to-End Automation"},
        ]
    },
    "skills": {
        "Data Engineering & Distributed Systems": [
            "Apache Spark",
            "PySpark",
            "Scala",
            "Python Programming",
            "SQL Optimization",
            "ETL/ELT Pipeline Development",
            "Distributed Data Processing",
            "Databricks",
            "Starburst",
            "Snowflake",
            "Delta Lake",
            "Trino",
        ],
        "Cloud & Data Warehousing": [
            "Google Cloud Platform (GCP)",
            "BigQuery",
            "AWS S3",
            "Data Lake Architecture",
            "Apache Cassandra",
            "MySQL",
            "Elasticsearch",
            "Hadoop HDFS",
        ],
        "Workflow Orchestration & Streaming": [
            "Apache Airflow",
            "Apache Kafka",
            "Streaming Data Frameworks",
            "Apache ZooKeeper",
            "Confluent Schema Registry",
        ],
        "DevOps, CI/CD & Infrastructure": [
            "CI/CD and DevOps",
            "Git & GitLab",
            "Docker",
            "Kubernetes",
            "Terraform (IaC)",
            "Jenkins",
            "Ansible",
            "Rundeck",
        ],
        "Data Governance, Monitoring & Analytics": [
            "Data Quality and Governance",
            "Data Monitoring and Logging",
            "Prometheus & Grafana",
            "dbt",
            "Tableau",
            "Data Collaboration and Teamwork",
            "Agile / Scrum",
        ],
    },
    "languages": [
        {"name": "English", "level": "Full Professional Proficiency"},
        {"name": "French", "level": "Working Proficiency"},
        {"name": "Romanian", "level": "Native / Bilingual"},
    ],
    "experience": [
        {
            "role": "Big Data Engineer",
            "company": "IBM",
            "location": "Bucharest",
            "period": "Dec 2025 - Present",
            "is_current": True,
            "badge": "Current Role",
            "key_technologies": [
                "Apache Spark",
                "Scala",
                "Apache Airflow",
                "Snowflake",
                "Starburst",
                "AWS S3",
                "Databricks",
                "Terraform",
                "Python",
                "Git"
            ],
            "responsibilities": [
                "Design, build, and maintain scalable big data pipelines and platforms capable of processing high volumes of structured and unstructured data across distributed environments.",
                "Develop robust ETL/ELT workflows using Apache Spark and Scala to transform, enrich, and optimize large-scale datasets for analytics and operational use cases.",
                "Implement and orchestrate automated data workflows with Apache Airflow, ensuring reliable scheduling, monitoring, and dependency management across complex data ecosystems.",
                "Build and optimize cloud-based data lake and storage solutions leveraging S3 for scalable, secure, and cost-efficient data storage and retrieval.",
                "Enable high-performance distributed querying and analytics using Starburst and Snowflake to support business intelligence, reporting, and self-service analytics initiatives.",
                "Optimize data processing performance, scalability, and reliability across distributed systems through partitioning strategies, caching, parallelization, and resource tuning.",
                "Collaborate with data scientists, analysts, and software engineers to deliver trusted datasets and data products that support data-driven decision-making.",
                "Maintain version-controlled codebases and CI/CD workflows using Git to support collaborative development, code quality, and deployment automation.",
                "Troubleshoot and resolve pipeline failures, performance bottlenecks, and infrastructure issues within large-scale cloud and distributed data environments.",
                "Built and maintained Snowflake data pipelines using SQL and Python, implementing staged ingestion, incremental loading, data transformations, and warehouse optimization through workload-aware sizing and automated suspension of idle compute.",
                "Used AI-assisted development tools, such as JetBrains Assistant and Cursor, to accelerate implementation and refactoring, validating generated code through code reviews, automated tests, linting, and edge-case analysis.",
                "Worked with Terraform-managed infrastructure and infrastructure-as-code workflows to support data platform resources and controlled infrastructure changes, including defining Snowflake resources.",
                "Contributed to the migration of data processing pipelines to Databricks, adapting existing workloads to the Databricks environment and supporting scalable data transformations, processing reliability, and performance optimization."
            ]
        },
        {
            "role": "Senior Data Engineer",
            "company": "eMAG",
            "location": "Bucharest",
            "period": "Jun 2024 - Dec 2025",
            "is_current": False,
            "key_technologies": [
                "GCP",
                "BigQuery",
                "PySpark",
                "Apache Spark",
                "Apache Airflow",
                "Python",
                "SQL",
                "Docker",
                "Kubernetes",
                "Jenkins",
                "Prometheus",
                "Grafana",
                "dbt",
                "Tableau"
            ],
            "responsibilities": [
                "Design, develop, and maintain scalable ETL/ELT pipelines using SQL, Python, PySpark, and Apache Spark for large-scale data processing and transformation.",
                "Build and orchestrate automated workflows using Apache Airflow, including DAG development, scheduling, monitoring, retry handling, and dependency management.",
                "Develop cloud-native data solutions on Google Cloud Platform (GCP) using BigQuery.",
                "Optimize complex SQL queries, BigQuery performance, partitioning, clustering, indexing strategies, and cost-efficient data warehouse architectures.",
                "Work with distributed data processing technologies including PySpark, Hadoop, Hive, Kafka, and streaming frameworks for high-volume batch and realtime pipelines.",
                "Integrate data from APIs, relational databases, NoSQL systems, SaaS platforms, and cloud storage solutions using Python-based ingestion frameworks.",
                "Implement CI/CD and DevOps/DataOps practices using Git, GitLab, Jenkins, Docker, Kubernetes, and Infrastructure-as-Code methodologies.",
                "Build reusable Python modules, data validation frameworks, logging systems, and monitoring solutions using tools such as Prometheus and Grafana.",
                "Support analytics and machine learning workloads by preparing curated datasets and enabling integrations with tools such as dbt and Tableau.",
                "Ensure data quality, governance, security, lineage, and compliance through automated testing, metadata management, IAM controls, and enterprise data governance standards.",
                "Collaborate with data analysts, data scientists, software engineers, and business stakeholders in Agile/Scrum environments to deliver scalable and reliable data platforms.",
                "Provide technical leadership, code reviews, architecture guidance, troubleshooting, and performance tuning across enterprise-scale cloud data ecosystems."
            ]
        },
        {
            "role": "Big Data Developer",
            "company": "Orange Services",
            "location": "Bucharest",
            "period": "Jun 2019 - Jun 2024",
            "is_current": False,
            "key_technologies": [
                "Apache Spark",
                "Scala",
                "Kafka",
                "Cassandra",
                "Delta Lake",
                "Trino",
                "AWS S3",
                "HDFS",
                "Kubernetes",
                "Ansible",
                "Jenkins",
                "Rundeck",
                "Python"
            ],
            "responsibilities": [
                "Developed and maintained Big Data solutions for an IoT management platform within an Agile environment.",
                "Designed and implemented both batch and real-time streaming data pipelines.",
                "Processed and transformed large-scale datasets, to the tune of 1 billion rows a day, to support downstream teams and business applications.",
                "Built near real-time data aggregation and transformation workflows using Apache Spark and Scala.",
                "Developed stateless and stateful streaming applications for continuous event processing.",
                "Implemented real-time alerting systems based on predefined operational parameters and thresholds.",
                "Developed and maintained Python scripts for data processing, automation, monitoring, and operational support tasks.",
                "Integrated distributed messaging and streaming technologies such as Apache Kafka and Apache ZooKeeper.",
                "Managed data serialization and schema evolution using Confluent Schema Registry.",
                "Worked with distributed storage and database technologies including Apache Cassandra, Delta Lake, MySQL, and Elasticsearch.",
                "Utilized cloud and distributed file storage systems such as Amazon Web Services S3 and Apache Hadoop HDFS.",
                "Deployed and managed applications in containerized environments using Kubernetes.",
                "Automated deployment and infrastructure management tasks using Ansible.",
                "Supported CI/CD processes and operational workflows using Jenkins and Rundeck.",
                "Contributed to data warehousing, reporting, and analytical workloads by querying and federating data across multiple storage systems using Trino.",
                "Collaborated cross-functionally with engineering and analytics teams to deliver scalable and reliable data processing solutions."
            ]
        },
        {
            "role": "Technician",
            "company": "alfrednet",
            "location": "Bucharest",
            "period": "May 2018 - Jun 2019",
            "is_current": False,
            "key_technologies": [
                "Access Control",
                "Security Systems",
                "SOAP Protocol",
                "Hardware / Network Setup"
            ],
            "responsibilities": [
                "Set up Access Control Systems and tested security camera systems.",
                "Researched ways to interface with the camera systems via SOAP protocol to enhance system functionality.",
                "Conducted off-site camera installations for local businesses to expand company's service offerings."
            ]
        }
    ],
    "education": [
        {
            "degree": "Bachelor of Engineering - BE, Computer Science And Engineering",
            "institution": "Facultatea de Automatică și Calculatoare, UPB",
            "location": "Bucharest, Romania",
            "period": "Jan 2018 - Jul 2022"
        },
        {
            "degree": "BS, Computer Science",
            "institution": "New York University - Polytechnic School of Engineering",
            "location": "New York, USA",
            "period": "Jan 2015 - Dec 2016"
        },
        {
            "degree": "Mathematics and Computer Science",
            "institution": "ICHB",
            "location": "Bucharest, Romania",
            "period": "Jan 2011 - Dec 2015"
        }
    ],
    "certifications": [
        {
            "title": "Databricks Certified Data Engineer Associate",
            "issuer": "Databricks",
            "date": "Oct 2026",
            "badge": "Associate"
        },
        {
            "title": "Astronomer Certification DAG Authoring for Apache Airflow",
            "issuer": "Astronomer",
            "date": "Dec 2024",
            "badge": "DAG Authoring"
        },
        {
            "title": "Astronomer Certification for Apache Airflow Fundamentals",
            "issuer": "Astronomer",
            "date": "Jun 2024",
            "badge": "Fundamentals"
        },
        {
            "title": "Certified SAFe® 5 Practitioner",
            "issuer": "Scaled Agile, Inc.",
            "date": "May 2023",
            "badge": "SAFe 5"
        }
    ],
    "courses": [
        "Foundations in Management",
        "General Engineering",
        "Introduction to Programming",
        "Object Oriented Programming"
    ]
}
