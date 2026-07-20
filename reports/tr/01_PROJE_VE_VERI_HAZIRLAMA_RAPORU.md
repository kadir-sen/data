# Sales Data Exercise — Proje ve Veri Hazırlama Raporu

## 1. Bu çalışmanın gerçek amacı nedir?

Bu çalışma ilk bakışta birkaç `SUM`, `GROUP BY`, `COUNT DISTINCT` ve sıralama işleminden oluşuyor gibi görünür. Fakat değerlendirilmek istenen temel beceri, matematiksel karmaşıklık değil; **ham bir operasyonel satış exportunu güvenilir, tekrar üretilebilir ve denetlenebilir bir raporlama veri setine dönüştürme becerisidir.**

İşverenin sorduğu “en çok satan ürün hangisi?”, “en yoğun saat hangisi?” gibi soruların hesaplaması kolaydır. Asıl zorluk, bu soruları yanlış grain, kirli ürün kodları, duplicate satırlar ve güvenilmez gelir alanı üzerinden cevaplamamaktır.

Bu nedenle proje şu sırayla ele alındı:

1. Kaynak dosyanın gerçekten aynı dosya olduğunun doğrulanması.
2. Satır grain’inin ve business key’lerin anlaşılması.
3. Ham veri profilinin çıkarılması.
4. Veri kalitesi sorunlarının sınıflandırılması.
5. Ham alanlar korunarak temiz alanların üretilmesi.
6. Hariç tutulan kayıtların açıkça kaydedilmesi.
7. Ham → dahil edilen → hariç tutulan mutabakatının yapılması.
8. İşverenin analiz sorularının yalnızca temiz veri üzerinden cevaplanması.
9. Sonuçların kaynak satırlara kadar izlenebilir bırakılması.
10. Forecasting gibi ileri çalışmaların, temel veri güvenilirliği tamamlandıktan sonra ayrı bir uzantı olarak tasarlanması.

---

## 2. Kaynak dosyanın kimliği

Kaynak dosya, sipariş kalemi seviyesinde hazırlanmış bir CSV exportudur.

Doğrulanan özellikler:

| Özellik | Değer |
|---|---:|
| Dosya boyutu | 1.201.875 bayt |
| CSV satırı | 10.001 — başlık dahil |
| Veri satırı | 10.000 |
| Kolon sayısı | 9 |
| SHA-256 | `b49ade73e618ea4ec9592f60c9ce4d775df75661ccdb2fc62d35dffd011efa35` |
| İlk tarih | 2026-01-01 02:27:07 |
| Son tarih | 2026-07-10 23:58:31 |
| Kapsanan takvim günü | 191 |
| Store değeri | Yalnızca `Printualist` |

SHA-256 kontrolü önemlidir. Çünkü aynı isimde farklı bir dosya kullanılırsa tüm analiz sonuçları değişebilir. Dosya adı tek başına kaynak kimliği değildir. Checksum, kaynağın bayt seviyesinde değişmediğini gösterir.

Repo içinde dosya, API boyut sınırları nedeniyle base64 + bzip2 parçaları halinde saklanacak ve `scripts/reconstruct_sales_data.py` ile birebir yeniden üretilecektir. Script yalnızca şu üç kontrol geçerse CSV’yi geçerli kabul eder:

- SHA-256 doğru mu?
- Bayt sayısı doğru mu?
- Başlık dahil satır sayısı doğru mu?

Bu yaklaşım bir veri temizleme işlemi değildir; yalnızca **kaynak bütünlüğü kontrolüdür**.

---

## 3. Veri setinin grain’i: bir satır neyi temsil ediyor?

Veri setindeki bir satır, bir sipariş değil; **bir sipariş kalemidir**.

Bu ayrım kritik önemdedir:

- `order_id`: Siparişi tanımlar. Bir siparişte birden fazla ürün varsa tekrar edebilir.
- `order_item_id`: Sipariş içindeki tek bir ürün satırını tanımlar. Temiz exportta benzersiz olması beklenir.

Temiz veride:

| Ölçü | Değer |
|---|---:|
| Temiz sipariş kalemi | 9.988 |
| Farklı sipariş | 9.388 |
| Satır ile sipariş arasındaki fark | 600 |

Bu, bazı siparişlerin birden fazla ürün kalemi içerdiğini gösterir.

### Neden önemli?

Aşağıdaki hesap yanlış olur:

```python
hourly_orders = df.groupby("hour").size()
```

Bu kod saatlik **satır sayısını** verir. Çok ürünlü siparişler birden fazla sayılır.

Doğru hesap şudur:

```python
hourly_orders = (
    df.groupby("hour")["order_id"]
      .nunique()
)
```

Yani “kaç sipariş geldi?” sorusu için `COUNT(DISTINCT order_id)` kullanılır. “Kaç sipariş kalemi var?” sorusu için satır sayısı kullanılır.

---

## 4. Kaynak kolonların iş anlamı

| Kolon | İş anlamı | Temel risk | Temizlemedeki yaklaşım |
|---|---|---|---|
| `order_datetime` | Sipariş zamanı | Timezone yanlış yorumlanabilir | America/Los_Angeles yerel saat olarak korunur |
| `order_id` | Sipariş anahtarı | Tekrarı yanlışlıkla duplicate sanılabilir | Tekrarına izin verilir |
| `order_item_id` | Sipariş kalemi anahtarı | Aynı satır exportta çoğalabilir | Duplicate sınıflandırmasının business key’i |
| `store` | Satış mağazası/kanalı | Çoklu kanal varsayımı yapılabilir | Bu dosyada yalnızca Printualist olduğu belirtilir |
| `item_code` | Satılabilir child SKU | Renk/beden yanlış ayrıştırılabilir | Sağdan suffix mantığıyla parse edilir |
| `parent_sku` | Ürün ailesi | Yazım varyantları ürünleri böler | Canonical parent alanı üretilir |
| `qty` | Satılan adet | Metin/negatif/sıfır olabilir | Pozitif integer doğrulaması |
| `unit_price` | USD birim fiyat | Metin/negatif olabilir | Decimal tabanlı doğrulama |
| `line_total` | Kaynak satır geliri | Format bozuk olabilir | Ham değer korunur, temiz gelir yeniden hesaplanır |

Her ham alan korunur. Temizleme, ham değeri silip yerine başka bir değer yazmak değildir. Örneğin:

```text
parent_sku_raw   = tm-6215-multi
parent_sku_clean = TM-6215-MULTI
issue_code       = PARENT_CASE_NORMALIZED
```

Bu yapı sayesinde raporun neden değiştiği geriye doğru izlenebilir.

---

## 5. Neden source_row_number eklendi?

CSV’deki her veri satırına, başlık dahil gerçek dosya satırını gösterecek şekilde `source_row_number` eklendi.

- CSV başlığı: satır 1
- İlk veri kaydı: source row 2
- Son veri kaydı: source row 10.001

Bu alanın amacı şudur:

> “Bu gelir neden değişti?” veya “Bu ürün hangi ham kayıt yüzünden eşlendi?” sorusu geldiğinde, temiz çıktının kaynak CSV’deki gerçek satırına dönülebilmesi.

Raporlama güvenilirliğinde bu özellik **lineage** olarak adlandırılır.

---

## 6. İş akışının mimarisi

Projede önerilen ve kodlanan akış şöyledir:

```text
Sıkıştırılmış repo parçaları
        │
        ▼
reconstruct_sales_data.py
        │ checksum + byte + line count
        ▼
data/raw/sales_data.csv
        │ değişmeden korunur
        ▼
run_sales_exercise.py
        │
        ├── Veri tipi doğrulaması
        ├── Duplicate sınıflandırması
        ├── Parent SKU canonicalization
        ├── Renk / beden ayrıştırma
        ├── Gelir yeniden hesaplama
        ├── Yerel zaman alanları
        ├── Issue code üretimi
        └── Reconciliation assertionları
        │
        ▼
data/processed/
        ├── cleaned_sales.csv
        ├── excluded_rows.csv
        ├── issue_log.csv
        ├── reconciliation.csv
        ├── run_manifest.json
        └── analysis/*.csv
```

Bu yapıda notebook veya manuel Excel düzeltmesi source of truth değildir. Aynı komut aynı input üzerinde çalıştırıldığında aynı sonucu üretmelidir.

---

## 7. Ham veride bulunan ana sorunların özeti

### 7.1 Parent SKU dağınıklığı

Ham veride 32 farklı `parent_sku` metni görünmesine rağmen, item code yapısı gerçekte 9 ürün ailesine işaret etmektedir.

| Durum | Etkilenen satır |
|---|---:|
| Sorunsuz parent | 8.290 |
| Sonda boşluk | 346 |
| Alt çizgi yerine tire ihtiyacı | 287 |
| Küçük/büyük harf farkı | 287 |
| Eksik tire | 274 |
| Türkçe `İ` karakteri | 186 |
| Çift tire | 182 |
| İşletme teyidi gerektiren HP kodu | 120 |
| Parent alanında child SKU | 16 |
| Parent boş | 12 |
| **Toplam düzeltme/inceleme gerektiren** | **1.710** |

Bu sorun çözülmeden yapılan pivot, aynı ürünü farklı ürünlermiş gibi parçalar.

### 7.2 Duplicate order item

- 12 farklı `order_item_id` iki kez bulunmuştur.
- Duplicate gruplarındaki tüm iş alanları birebir aynıdır.
- Conflicting duplicate yoktur.
- Her grupta ilk satır deterministik olarak tutulmuş, ikinci kopya hariç bırakılmıştır.

Hariç tutmanın etkisi:

| Ölçü | Etki |
|---|---:|
| Satır | 12 |
| Adet | 17 |
| Gelir | 356,88 USD |

### 7.3 `line_total` format sorunları

Kaynak `line_total` alanında 6 kalite problemi vardır:

| Source row | Ham değer | qty | unit_price | Hesaplanan doğru gelir | Sorun |
|---:|---|---:|---:|---:|---|
| 1.640 | `84,08` | 2 | 42,04 | 84,08 | Virgüllü locale formatı |
| 2.111 | `1.234,56` | 2 | 27,98 | 55,96 | Belirsiz locale; ham sayı iş kuralıyla çelişiyor |
| 4.052 | `-` | 2 | 19,34 | 38,68 | Sayısal değil |
| 4.767 | ` 14.13 ` | 1 | 14,13 | 14,13 | Gereksiz whitespace |
| 6.891 | `N/A` | 2 | 12,64 | 25,28 | Sayısal değil |
| 9.497 | boş | 1 | 14,35 | 14,35 | Eksik değer |

Parse edilebilen diğer `line_total` değerlerinin tamamı `qty × unit_price` ile uyumludur.

### 7.4 Renk ve beden

- 248 farklı child SKU vardır.
- 8 renk vardır.
- Geçerli beden seti: `XS, S, M, L, XL, 2XL, 3XL`.
- Bütün child SKU’lar sağdan ayrıştırma kuralıyla parse edilebilmiştir.

Renkler:

```text
Black, Charcoal, IrishGreen, Navy, Red, RoyalBlue, Sand, White
```

---

## 8. Neden parent SKU doğrudan TRIM/UPPER ile çözülmedi?

Basit metin normalizasyonu şu sorunları çözebilir:

- sonda boşluk,
- case farkı,
- `_` → `-`,
- `--` → `-`,
- `İ` → `I`.

Ancak şu sorunları tek başına çözemez:

- parent boşsa hangi ürün ailesi olduğu,
- parent alanına child SKU yazıldıysa gerçek parent,
- `HP-MERCHIZE-BAJE01` değerinin resmi kodunun `HP-MERCHIZE-BAJE-01` olup olmadığı.

Bu nedenle canonical parent, kontrollü bir **item_code prefix mapping** ile üretilmiştir. Böylece child SKU’nun ait olduğu ürün ailesi deterministik biçimde çıkarılır.

Örnek:

```text
item_code:  TM-6215-White-L
raw parent: tm-6215-multi
clean:      TM-6215-MULTI
method:     ITEM_CODE_PREFIX:TM-6215-
issue:      PARENT_CASE_NORMALIZED
```

Gerçek üretim ortamında bu mapping kod içine gömülü olmamalı; product master tablosundan gelmelidir. Bu exercise için mapping tablosu, product master davranışının kontrollü simülasyonudur.

---

## 9. Neden temiz gelir `qty × unit_price` olarak hesaplandı?

Assignment açıkça bu egzersizde indirim ve vergi bulunmadığını belirtmektedir. Dolayısıyla iş kuralı:

```text
line_total_expected = qty × unit_price
```

`line_total` ham metnini zorla locale tahminleriyle parse etmek daha risklidir.

Örneğin:

```text
raw line_total = 1.234,56
qty            = 2
unit_price     = 27.98
```

Bu ham değer Avrupa formatında 1.234,56 olarak yorumlanırsa, iş kuralıyla tamamen çelişir. Doğru gelir:

```text
2 × 27.98 = 55.96
```

Bu nedenle:

- `line_total_raw` korunur,
- parse sonucu ayrı alanda tutulur,
- `line_total_calculated` hesaplanır,
- delta ve match flag oluşturulur,
- raporda `line_total_clean = line_total_calculated` kullanılır.

Para hesaplarında binary floating-point yerine Decimal tercih edilmesi, 0,1 + 0,2 gibi temsil hatalarını azaltır.

---

## 10. Duplicate neden yalnızca `drop_duplicates()` ile silinmedi?

Aynı `order_item_id` iki şekilde tekrar edebilir:

### Exact duplicate

Tüm iş alanları aynıdır. Export replay veya join çoğalması gibi bir problem olabilir. Bir kayıt tutulabilir.

### Conflicting duplicate

Aynı `order_item_id` altında farklı ürün, adet, fiyat veya tarih vardır. Hangi kaydın doğru olduğu veri içinden bilinemez.

Pipeline önce her duplicate grubundaki tüm iş alanlarını karşılaştırır:

```text
UNIQUE
EXACT_DUPLICATE_KEEP
EXACT_DUPLICATE_EXCLUDE
CONFLICTING_DUPLICATE
```

Bu dosyada conflicting duplicate bulunmadığı için 12 exact kopya güvenle hariç tutulmuştur. Conflicting duplicate bulunsaydı pipeline duracak ve business decision isteyecekti.

---

## 11. Reconciliation: ham veri nasıl temiz veriye bağlandı?

Temizleme sonunda mutabakat şöyledir:

| Veri katmanı | Satır | Adet | Gelir |
|---|---:|---:|---:|
| Ham | 10.000 | 13.631 | 227.841,15 USD |
| Hariç tutulan exact duplicate | 12 | 17 | 356,88 USD |
| **Temiz dahil edilen** | **9.988** | **13.614** | **227.484,27 USD** |

Kontroller:

```text
10.000 = 9.988 + 12
13.631 = 13.614 + 17
227.841,15 = 227.484,27 + 356,88
```

Bu üç eşitlik assertion olarak çalıştırılır. Böylece temizleme sırasında kayıt, adet veya gelir kaybolmadığı kanıtlanır.

---

## 12. Üretilen temel veri alanları

Temiz dataset ham alanlara ek olarak şunları içerir:

- `source_row_number`
- `qty_clean`
- `unit_price_clean`
- `line_total_parsed`
- `line_total_calculated`
- `line_total_delta`
- `line_total_match_flag`
- `line_total_clean`
- `parent_sku_normalized_text`
- `parent_sku_clean`
- `parent_mapping_method`
- `parent_issue_code`
- `parent_mapping_requires_confirmation`
- `color_clean`
- `size_clean`
- `is_one_size`
- `variant_key`
- `order_datetime_local`
- `order_date_local`
- `order_hour_local`
- `order_hour_bucket_local`
- `weekday_number`
- `weekday_name`
- `is_weekend`
- `month_local`
- `duplicate_group_size`
- `duplicate_rank`
- `duplicate_classification`
- `include_flag`
- `exclusion_reason`
- `issue_codes`

Bu yaklaşım, “ham veriyi düzelttim” demek yerine **hamdan temize dönüşümü açıklanabilir bir model** haline getirir.

---

## 13. Çalıştırma

```bash
python scripts/reconstruct_sales_data.py
python scripts/run_sales_exercise.py
```

Beklenen ana çıktılar:

```text
data/raw/sales_data.csv
data/processed/cleaned_sales.csv
data/processed/excluded_rows.csv
data/processed/issue_log.csv
data/processed/reconciliation.csv
data/processed/run_manifest.json
data/processed/analysis/parent_summary.csv
data/processed/analysis/color_summary.csv
data/processed/analysis/parent_color_winners.csv
data/processed/analysis/hourly_distinct_orders.csv
data/processed/analysis/dated_hour_distinct_orders.csv
data/processed/analysis/monthly_summary.csv
data/processed/analysis/weekday_summary.csv
data/processed/analysis/analysis_summary.json
```

---

## 14. Bu aşamadan öğrenilmesi gereken veri prensipleri

1. **Önce grain, sonra metrik.** Satırın neyi temsil ettiğini bilmeden aggregate yapılmaz.
2. **Business key ile teknik satır aynı değildir.** `order_item_id` duplicate kontrolünün anahtarıdır.
3. **Ham alanı silme; temiz alan üret.** İzlenebilirlik korunur.
4. **Dimension kirliyse ranking yanlıştır.** Parent SKU temizlenmeden ürün lideri hesaplanmaz.
5. **İş kuralı, agresif parsing’den daha güvenilir olabilir.** Burada gelir `qty × unit_price` üzerinden kurulmuştur.
6. **Her exclusion reconcile edilmelidir.** “12 satırı sildim” yeterli değildir; adet ve gelir etkisi de açıklanır.
7. **Belirsizlik otomatik karara dönüştürülmemelidir.** HP canonical kodu gibi konular business confirmation olarak işaretlenir.
8. **Reproducibility teslimatın parçasıdır.** Aynı kaynak dosya aynı komutla aynı çıktıyı üretmelidir.
