import dns.resolver
import concurrent.futures

# use the system's configured resolver (e.g. the corporate DNS) instead of
# sending every scanned domain to a hard-coded public resolver
my_resolver = dns.resolver.Resolver()
my_resolver.lifetime = 10

def query(domain, record_type):
    try:
        return [x.to_text() for x in my_resolver.resolve(domain, record_type)]
    except Exception as e:
        return []

def get_dns(domain):
    record_types = ['MX', 'NS', 'TXT', 'SOA', 'CNAME']
    results = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        future_to_record = {executor.submit(query, domain, record_type): record_type for record_type in record_types}
        for future in concurrent.futures.as_completed(future_to_record):
            record_type = future_to_record[future]
            try:
                results[record_type] = future.result()
            except Exception as e:
                results[record_type] = []

    return results