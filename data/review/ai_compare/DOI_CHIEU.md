# Đối chiếu nhãn CAP giữa 2 AI: claude-opus-5-5, gemini

- Số khoản: **218** · đồng thuận hoàn toàn: **194** (89.0%) · bất đồng (người quyết): **24**
- Đồng thuận riêng câu (1) Quan sát được: 90.4% · Cohen's kappa: claude-opus-5-5 vs gemini = 0.3705
- Kiểm ngẫu nhiên trong nhóm đồng thuận: **20** khoản (seed 2018) — tỉ lệ sai trong mẫu này phải báo cáo (hướng dẫn mục 10.6).

## Khoản bất đồng

### R1306:Art63(1)

> 1. Where it is found that a beneficiary does not comply with the eligibility criteria, commitments or other obligations relating to the conditions for the granting of the aid or support, as provided for in the sectoral agricultural legislation, the aid shall not be paid or shall be withdrawn in full or in part and, where relevant, the corresponding payment entitlements as referred to in Article 21 of Regulation (EU) No 1307/2013 shall not be allocated or shall be withdrawn. ( 1 ) Regulation (EU) No 952/2013 of the European Parliament and of the Council of 9 October 2013 laying down the Union C…

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Nghĩa vụ không chi / thu hồi khi phát hiện không tuân thủ, nhưng log không ghi việc "phát hiện không đáp ứng điều kiện" (mã penalty không công bố nghĩa, case:rejected không rõ là từ chối toàn phần) và chi trả từng phần vẫn được phép, nên không viết được ràng buộc chắc chắn.*
- **gemini**: Có · Not Co-Existence(Payment application / Application / begin payment, Payment application / Application / finish payment) | case:rejected == True · tham chiếu: Không · TB · *Khi người thụ hưởng không tuân thủ điều kiện đủ tư cách (proxy: case:rejected == True ≈ không đáp ứng điều kiện hưởng hỗ trợ), khoản viện trợ không được phép chi trả (proxy: Payment application / Application / begin payment và Payment application / Application / finish payment ≈ chi trả viện trợ).*
  - ⚠ LỖI: Not Co-Existence(Payment application / Application / begin payment, Payment application / Application / finish payment) | case:rejected == True (Activity 'Payment application / Application / begin payment, Payment application)

### R1307:Art10(1)

> 1. Member States shall decide in which one of the following cases not to grant direct payments to a farmer: (a) where the total amount of direct payments claimed or due to be granted before the application of Article 63 of Regulation (EU) No 1306/2013 in a given calendar year is less than EUR 100; (b) where the eligible area of the holding for which direct payments are claimed or due to be granted before the application of Article 63 of Regulation (EU) No 1306/2013 is less than one hectare.

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Log có case:area và số tiền, nhưng khoản để Nhà nước thành viên chọn MỘT trong hai ngưỡng (EUR 100 hoặc 1 ha) và luật không nói Đức chọn ngưỡng nào, nên không viết được ràng buộc xác định.*
- **gemini**: Không · — · tham chiếu: — · TB · *Khoản này yêu cầu Nhà nước thành viên chọn một trong hai ngưỡng tối thiểu (100 EUR hoặc 1 ha) để từ chối chi trả trực tiếp, nhưng văn bản luật không xác định bang của Đức trong log đã chọn phương án hay con số cụ thể nào.*

### R1307:Art24(1)

> 1. Payment entitlements shall be allocated to farmers who are entitled to be granted direct payments in accordance with Article 9 of this Regulation provided that: (a) they apply for allocation of payment entitlements under the basic payment scheme by the final date for submission of applications in 2015 to be set in accordance with point (b) of the first subparagraph of Article 78 of Regulation (EU) No 1306/2013, except in case of force majeure or exceptional circumstances; and (b) they were entitled to receive payments, before any reduction or exclusion provided for in Chapter 4 of Title II …

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Phân bổ quyền hưởng khi nông dân nộp đơn trước hạn chót năm 2015, nhưng hạn chót do văn bản thực thi theo Art78(b) ấn định, không có trong khoản hay khoản dẫn chiếu; điều kiện (b) về chi trả năm 2013 không có trong log.*
- **gemini**: Có · Precedence(Entitlement application / Main / initialize → Entitlement application / Main / decide) | case:year == 2015 · tham chiếu: Không · TB · *Theo điểm (a) khoản 1, quyền hưởng thanh toán chỉ được phân bổ nếu nông dân nộp đơn xin phân bổ trong năm 2015 (proxy: Entitlement application / Main / initialize ≈ nộp đơn xin phân bổ quyền hưởng thanh toán; proxy: Entitlement application / Main / decide ≈ quyết định phân bổ quyền hưởng thanh toán).*

### R1307:Art32(1)

> 1. Support under the basic payment scheme shall be granted to farmers, by means of declaration in accordance with Article 33(1), upon activation of a payment entitlement per eligible hectare in the Member State where it has been allocated. Activated payment entitlements shall give a right to the annual payment of the amounts fixed therein, without prejudice to the application of financial discipline, of reduction of payments in accordance with Article 11 and of linear reductions in accordance with Article 7, Article 51(2) and point (c) of Article 65(2) of this Regulation, and to the applicatio…

- **claude-opus-5-5**: Có · Precedence({Parcel document / Main / finish editing | Geo parcel document / Declared / finish editing} → Payment application / Application / begin payment) · tham chiếu: Một phần · Thấp · *Hỗ trợ chi trả cơ bản chỉ được cấp qua khai báo theo Art33(1); đối tượng khai báo (các thửa đất tương ứng số ha hợp lệ) lấy từ Art33(1). proxy: Parcel document / Main / finish editing, Geo parcel document / Declared / finish editing ≈ hoàn tất khai báo thửa đất; proxy: Payment application / Application / begin payment ≈ cấp chi trả; phần kích hoạt quyền hưởng không có trong log.*
- **gemini**: Có · Precedence(Geo parcel document / Declared / create → Payment application / Application / begin payment) | case:basic payment == True · tham chiếu: Có · TB · *Hỗ trợ theo chương trình thanh toán cơ bản chỉ được cấp khi nông dân kích hoạt quyền hưởng thông qua việc kê khai các thửa đất tương ứng với diện tích hợp lệ lấy từ R1307:Art33(1) (proxy: Geo parcel document / Declared / create ≈ kê khai thửa đất để kích hoạt quyền hưởng; proxy: Payment application / Application / begin payment ≈ chi trả hỗ trợ).*

### R1307:Art33(1)

> 1. For the purposes of the activation of payment entitlements provided for in Article 32(1), the farmer shall declare the parcels corresponding to the eligible hectares accompanying any payment entitlement. Except in the case of force majeure or exceptional circumstances, the parcels declared shall be at the farmer's disposal on a date fixed by the Member State, which shall be no later than the date fixed in that Member State for amending the aid application as referred to in Article 72(1) of Regulation (EU) No 1306/2013.

- **claude-opus-5-5**: Có · Responded Existence(Payment application / Application / mail income → {Parcel document / Main / initialize | Geo parcel document / Declared / create}) | case:basic payment == True · tham chiếu: Không · Thấp · *Nông dân phải khai báo các thửa đất ứng với số ha hợp lệ để kích hoạt quyền hưởng. proxy: Parcel document / Main / initialize, Geo parcel document / Declared / create ≈ khai báo thửa đất (Parcel document năm 2015, Geo parcel document 2016–2017); điều kiện thửa đất thuộc quyền sử dụng tại ngày Nhà nước ấn định không có trong log.*
- **gemini**: Có · Existence(Geo parcel document / Declared / create) | case:basic payment == True · tham chiếu: Không · TB · *Để kích hoạt quyền hưởng thanh toán theo chương trình thanh toán cơ bản, nông dân bắt buộc phải kê khai các thửa đất tương ứng với số héc-ta hợp lệ (proxy: Geo parcel document / Declared / create ≈ kê khai thửa đất).*

### R1307:Art41(3)

> 3. Without prejudice to the application of financial discipline, of reduction of payments in accordance with Article 11, of linear reductions as referred in Article 7 of this Regulation, and to the application of Article 63 of Regulation (EU) No 1306/2013, the redistributive payment shall be granted annually upon activation of payment entitlements by the farmer, or, in Member States applying Article 36 of this Regulation, upon declaration of eligible hectares by the farmer.

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Chi trả tái phân phối được cấp hằng năm khi nông dân kích hoạt quyền hưởng; log có case:redistribution nhưng không có sự kiện kích hoạt quyền hưởng, và thời điểm chi trả không được luật nối với activity cụ thể nào.*
- **gemini**: Có · Precedence(Geo parcel document / Declared / create → Payment application / Application / begin payment) | case:redistribution == True · tham chiếu: Có · TB · *Khoản thanh toán phân phối lại (`case:redistribution == True`) được cấp hàng năm khi nông dân kích hoạt quyền hưởng thanh toán hoặc kê khai héc-ta hợp lệ như quy định tại R1307:Art36(2) (proxy: Geo parcel document / Declared / create ≈ kê khai thửa đất / kích hoạt quyền hưởng; proxy: Payment application / Application / begin payment ≈ cấp thanh toán).*

### R1307:Art43(9)

> 9. Without prejudice to paragraphs 10 and 11 of this Article, to the application of financial discipline and of linear reductions in accordance with Article 7 of this Regulation and to the application of Article 63 of Regulation (EU) No 1306/2013, Member States shall grant the payment referred to in this Chapter to farmers who observe the practices referred to in paragraph 1 of this Article that are relevant for them, and to the extent that those farmers comply with Articles 44, 45 and 46 of this Regulation. This payment shall take the form of an annual payment per eligible hectare declared in…

- **claude-opus-5-5**: Không · — · tham chiếu: — · TB · *Nghĩa vụ chi trả greening phụ thuộc việc nông dân tuân thủ các thực hành Điều 44–46 và cách tính số tiền theo Điều 47; log không ghi nội dung thực hành canh tác, cũng không tách khoản chi greening (case:greening chỉ là cờ chương trình) nên không kiểm được theo từng hồ sơ.*
- **gemini**: Có · Precedence(Geo parcel document / Declared / create → Payment application / Application / begin payment) | case:greening == True · tham chiếu: Có · TB · *Khoản thanh toán xanh hóa (`case:greening == True`) được cấp hàng năm trên mỗi héc-ta hợp lệ được nông dân kê khai theo R1307:Art33(1) hoặc R1307:Art36(2) (proxy: Geo parcel document / Declared / create ≈ kê khai diện tích hợp lệ; proxy: Payment application / Application / begin payment ≈ cấp khoản thanh toán).*

### R1307:Art50(4)

> 4. Without prejudice to the application of financial discipline, of reduction of payments in accordance with Article 11 and of linear reductions in accordance with Article 7 of this Regulation, and to the application of Article 63 of Regulation (EU) No 1306/2013, the payment for young farmers shall be granted annually upon activation of payment entitlements by the farmer or, in Member States applying Article 36 of this Regulation, upon declaration of eligible hectares by the farmer.

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Khoản quy định khoản chi cho nông dân trẻ được cấp hằng năm khi kích hoạt quyền hưởng; log có cờ case:young farmer và các bước chi trả, nhưng việc chi bị bảo lưu bởi Điều 63 của 1306/2013 (có thể không chi khi không đủ điều kiện) và log không tách riêng khoản chi nông dân trẻ, nên không kiểm được chắc chắn theo hồ sơ.*
- **gemini**: Có · Precedence(Geo parcel document / Declared / create → Payment application / Application / begin payment) | case:young farmer == True · tham chiếu: Có · TB · *Khoản thanh toán cho nông dân trẻ (`case:young farmer == True`) được cấp hàng năm khi nông dân kích hoạt quyền hưởng thanh toán hoặc kê khai diện tích hợp lệ theo R1307:Art36(2) (proxy: Geo parcel document / Declared / create ≈ kê khai diện tích / kích hoạt quyền hưởng; proxy: Payment application / Application / begin payment ≈ cấp thanh toán).*

### R640:Art5(2)

> 2. Member States shall also ensure that agricultural parcels that are declared are reliably identified. They shall in particular require the aid applications and payment claims to be furnished with particular information or accompanied by documents specified by the competent authority that enable each agricultural parcel to be located and measured. For each reference parcel, Member States shall: (a) determine a maximum eligible area for the purpose of the support schemes listed in Annex I to Regulation (EU) No 1307/2013; (b) determine a maximum eligible area for the purpose of the area-related…

- **claude-opus-5-5**: Không · — · tham chiếu: — · Cao · *Nghĩa vụ của Nhà nước thành viên bảo đảm nhận dạng thửa đất và xác định diện tích hợp lệ tối đa, diện tích sinh thái, vùng đặc thù cho từng thửa tham chiếu — thuộc việc lập/duy trì LPIS, log không có dữ liệu thửa tham chiếu.*
- **gemini**: Có · Existence(Reference alignment / Main / performed) · tham chiếu: Không · Thấp · *Nhà nước thành viên phải đảm bảo các thửa đất kê khai được nhận dạng tin cậy và xác định diện tích hợp lệ tối đa cho từng thửa tham chiếu (proxy: Reference alignment / Main / performed ≈ thực hiện đối chiếu và xác định trên thửa tham chiếu).*

### R640:Art13(1)

> 1. Except in cases of force majeure and exceptional circumstances as referred to in Article 4, the submission of an aid application or payment claim pursuant to this Regulation after the final date for such submission as fixed by the Commission on the basis of Article 78(b) of Regulation (EU) No 1306/2013 shall lead to a 1 % reduction per working day of the amounts to which the beneficiary would have been entitled if the application or claim had been submitted within the time limit. Without prejudice to any particular measures to be taken by the Member States with regard to the need for the su…

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Có nghĩa vụ (nộp muộn giảm 1 %/ngày làm việc; muộn hơn 25 ngày lịch thì không được chi) và log có Payment application / Application / mail income, nhưng "final date" do Ủy ban ấn định không có trong khoản này hay trong R1306:Art78 được dẫn chiếu, nên không viết được mốc; log cũng chỉ có thời điểm hệ thống ghi nhận, không có ngày nộp, và không tách được mức giảm 1 %.*
- **gemini**: Không · — · tham chiếu: — · Cao · *Khoản này quy định mức giảm 1% mỗi ngày làm việc khi nộp đơn trễ và từ chối nếu trễ quá 25 ngày lịch sau hạn chót do Ủy ban/Nhà nước thành viên ấn định, nhưng cả khoản này lẫn khoản được dẫn chiếu R1306:Art78 đều không chứa ngày hạn chót cụ thể.*

### R640:Art13(3)

> 3. Except in cases of force majeure and exceptional circumstances as referred to in Article 4, the submission of an amendment to the single application or payment claim after the final date for such submission as fixed by the Commission on the basis of Article 78(b) of Regulation (EU) No 1306/2013 shall lead to a 1 % reduc tion per working day of the amounts relating to the actual use of the agricultural parcels concerned. Amendments to the single application or payment claim shall only be admissible until the latest possible date for late submission of the single application or payment claim …

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Có nghĩa vụ về sửa đổi đơn sau hạn (giảm 1 %/ngày làm việc, không chấp nhận sau hạn nộp muộn cuối cùng), có thể proxy Payment application / Change / initialize ≈ nộp sửa đổi đơn, nhưng ngày hạn chót không có trong khoản này hay trong R1306:Art78 được dẫn chiếu, nên không viết được ràng buộc ngày hợp lệ.*
- **gemini**: Không · — · tham chiếu: — · Cao · *Khoản này quy định mức giảm 1% mỗi ngày làm việc và tính hợp lệ khi nộp sửa đổi đơn trễ hạn, nhưng văn bản luật và khoản dẫn chiếu R1306:Art78 không nêu ngày hạn chót cụ thể.*

### R640:Art14

> Except in cases of force majeure and exceptional circumstances referred to in Article 4, the submission of an application for allocation or, when applicable, increase of the value of payment entitlements after the final date fixed for this purpose by the Commission on the basis of Article 78(b) of Regulation (EU) No 1306/2013, shall lead in that year to a 3 % reduction per working day of the amounts to be paid in respect of the payment entitlements or, when applicable, in respect of the increase of the value of payment entitlements to be allocated to the beneficiary. If such delay amounts to m…

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Khoản quy định giảm 3 %/ngày làm việc và quá 25 ngày lịch thì đơn xin quyền hưởng bị coi là không chấp nhận; nhưng hạn chót do Ủy ban ấn định (R1306 Art78(b)) không có ngày cụ thể trong khoản hay khoản được dẫn chiếu, và log không có tỉ lệ giảm theo quyền hưởng, nên không viết được ràng buộc với ngày hợp lệ.*
- **gemini**: Không · — · tham chiếu: — · Cao · *Khoản này quy định mức giảm 3% mỗi ngày làm việc và từ chối nếu trễ quá 25 ngày lịch khi nộp đơn xin phân bổ quyền hưởng thanh toán sau hạn chót, nhưng khoản luật và R1306:Art78 không có ngày hạn chót cụ thể.*

### R809:Art17(5)

> 5. The beneficiary shall unambiguously identify and declare the area of each agricultural parcel and, where applicable, the type, size and location of the ecological focus areas. With regard to the greening payment, the beneficiary shall also specify the use of the agricultural parcels declared. For this purpose, the beneficiary may confirm the information already provided in the pre-established form. However, where the information on the area, location or boundary of the agricultural parcel or, where applicable, the size and location of the ecological focus areas is not correct or is incomple…

- **claude-opus-5-5**: Không · — · tham chiếu: — · TB · *Nghĩa vụ khai báo diện tích, mục đích sử dụng từng thửa và sửa mẫu khi sai; log không ghi nội dung khai báo, cũng không có sự kiện đánh giá cập nhật thửa tham chiếu tương ứng.*
- **gemini**: Có · Existence(Geo parcel document / Declared / create) · tham chiếu: Không · Thấp · *Người thụ hưởng có nghĩa vụ xác định rõ ràng và kê khai diện tích của từng thửa đất nông nghiệp (proxy: Geo parcel document / Declared / create ≈ kê khai các thửa đất nông nghiệp).*

### R809:Art22(1)

> 1. Applications for allocation of payment entitlements or the increase of the value of payment entitlements under the basic payment scheme in accordance with Article 20, Article 24, Article 30, except paragraph 7(e), and Article 39 of Regulation (EU) No 1307/2013 shall be submitted by a date to be fixed by the Member States. The date fixed shall not be later than 15 May of the relevant calendar year. However, Estonia, Latvia, Lithuania, Finland and Sweden may fix a later date which shall not be later than 15 June of the relevant calendar year.

- **claude-opus-5-5**: Có · Absence(Entitlement application / Main / mail valid) với ngày(Entitlement application / Main / mail valid) > 15/05/năm · tham chiếu: Không · Thấp · *Đơn xin cấp/tăng giá trị quyền hưởng phải nộp trước ngày do Nhà nước ấn định, không muộn hơn 15/5 (ngày nằm ngay trong khoản; Đức không thuộc các nước được lùi đến 15/6); proxy: Entitlement application / Main / mail valid ≈ việc đơn xin quyền hưởng được nhận — không chắc thời điểm sự kiện trùng ngày nộp đơn.*
- **gemini**: Có · Existence(Entitlement application / Main / mail valid) với ngày(Entitlement application / Main / mail valid) <= 15/05/năm · tham chiếu: Không · TB · *Đơn xin phân bổ hoặc tăng giá trị quyền hưởng thanh toán theo chương trình thanh toán cơ bản phải được nộp chậm nhất vào ngày 15 tháng 5 của năm lịch liên quan tại Đức (proxy: Entitlement application / Main / mail valid ≈ nộp đơn xin phân bổ quyền hưởng thanh toán hợp lệ).*

### R809:Art28(1)

> 1. The administrative checks referred to in Article 74 of Regulation (EU) No 1306/2013, including cross-checks, shall permit the detection of non-compliances, in particular the automated detection using computerised means. The checks shall cover all elements that are possible and appropriate to control by means of administrative checks. They shall ensure that: (a) the eligibility criteria, commitments and other obligations for the aid scheme or support measure are fulfilled; (b) there is no double financing through other Union schemes; (c) the aid application or payment claim is complete and s…

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Khoản quy định phạm vi/nội dung kiểm tra hành chính (tiêu chí đủ điều kiện, không tài trợ kép, đơn đầy đủ và đúng hạn) nhưng không nêu thứ tự với chi trả hay thời hạn cụ thể; log không ghi nội dung kiểm tra nên chỉ kiểm được rất gián tiếp.*
- **gemini**: Có · Precedence(Control summary / Main / finish editing → Payment application / Application / begin payment) · tham chiếu: Có · Thấp · *Cơ quan chi trả phải thực hiện kiểm tra hành chính trên đơn xin hỗ trợ theo R1306:Art74 để đảm bảo đáp ứng đủ các điều kiện trước khi chi trả (proxy: Control summary / Main / finish editing ≈ hoàn tất kiểm tra hành chính; proxy: Payment application / Application / begin payment ≈ bắt đầu chi trả).*

### R809:Art29(1)

> 1. Where appropriate, the administrative checks shall include cross-checks: (a) on declared payment entitlements and on declared agricultural parcels, respectively, in order to avoid multiple granting of the same aid or support in respect of the same calendar or claim year and to prevent any undue accumulation of aid granted under area-related aid schemes listed in Annex I to Regulation (EU) No 1307/2013 and Annex VI to Council Regulation (EC) No 73/2009 ( 1 ), and area-related support measures as defined in point (21) of the second subparagraph of Article 2 of Delegated Regulation (EU) No 640…

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Kiểm tra chéo "where appropriate" với LPIS, quyền hưởng, hệ thống vật nuôi; Reference alignment / Main / performed có thể gần với kiểm tra chéo thửa đất (điểm c) nhưng khoản không nêu mốc thứ tự với chi trả, nội dung đối chiếu không có trong log.*
- **gemini**: Có · Precedence(Reference alignment / Main / performed → Payment application / Application / begin payment) · tham chiếu: Không · Thấp · *Điểm (c) quy định kiểm tra hành chính phải bao gồm kiểm tra chéo (giao cắt không gian) giữa các thửa đất kê khai trong đơn với hệ thống nhận dạng thửa đất nông nghiệp để xác minh tính hợp lệ (proxy: Reference alignment / Main / performed ≈ kiểm tra chéo với thửa tham chiếu; proxy: Payment application / Application / begin payment ≈ bắt đầu chi trả).*

### R809:Art71(6)

> 6. On-the-spot checks related to the sample provided for in Article 68(1) of this Regulation shall be carried out within the same calendar year where the aid applications, and/or payment claims are submitted or, as regards to the applications for the support schemes in the wine sector under Articles 46 and 47 of Regulation (EU) No 1308/2013, at any time during the period indicated in the second subparagraph of Article 97(1) of Regulation (EU) No 1306/2013.

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Kiểm tra tại chỗ cross-compliance phải làm trong cùng năm dương lịch nộp đơn; log có Inspection / On-Site / performed nhưng không rõ đó là kiểm tra cross-compliance (thuộc mẫu Art68(1)) hay kiểm tra điều kiện hưởng, và khoản không nêu ngày cụ thể nên không viết ràng buộc.*
- **gemini**: Có · Existence(Inspection / On-Site / performed) với ngày(Inspection / On-Site / performed) <= 31/12/năm | case:selected_random == True; Existence(Inspection / On-Site / performed) với ngày(Inspection / On-Site / performed) <= 31/12/năm | case:selected_risk == True · tham chiếu: Không · Thấp · *Các cuộc kiểm tra tại chỗ đối với mẫu được chọn phải được thực hiện trong cùng năm lịch nộp đơn xin hỗ trợ (proxy: Inspection / On-Site / performed ≈ thực hiện kiểm tra tại chỗ).*

### R809:Art72(1)

> 1. Every on-the-spot check carried out under this Title shall be the subject of a control report to be established by the competent control authority or under its responsibility. The report shall be divided into the following parts: (a) a general part containing, in particular, the following information: (i) the beneficiary selected for the on-the-spot check; (ii) the persons present; (iii) whether notice of the visit was given to the beneficiary and, if so, the period of advance prior notice; (b) a part reflecting separately the checks carried out in respect of each of the acts and standards …

- **claude-opus-5-5**: Không · — · tham chiếu: — · TB · *Mỗi lần kiểm tra tại chỗ phải có báo cáo kiểm tra với nội dung quy định; log không có nội dung giấy tờ hay sự kiện lập báo cáo kiểm tra cross-compliance (Inspection / On-Site / finish editing chỉ là bước chỉnh sửa, không chắc là báo cáo).*
- **gemini**: Có · Response(Inspection / On-Site / performed → Inspection / On-Site / finish editing) · tham chiếu: Không · Thấp · *Mọi cuộc kiểm tra tại chỗ phải được cơ quan kiểm soát lập thành báo cáo kiểm tra với các phần thông tin quy định (proxy: Inspection / On-Site / performed ≈ thực hiện kiểm tra tại chỗ; proxy: Inspection / On-Site / finish editing ≈ hoàn tất lập báo cáo kiểm tra tại chỗ).*

### R809:Art72(3)

> 3. The beneficiary shall be informed of any determined non-compliance within three months after the date of the on-the-spot check. Unless the beneficiary has taken immediate remedial action putting an end to the non-compliance found within the meaning of the second subparagraph of Article 99(2) of Regulation (EC) No 1306/2013, the beneficiary shall be informed within the time limit set in the first subparagraph of this paragraph that remedial action shall be taken pursuant to the second subparagraph of Article 99(2) of Regulation (EC) No 1306/2013. Unless the beneficiary has taken immediate re…

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Người hưởng phải được thông báo vi phạm trong ba tháng sau kiểm tra tại chỗ; log có Inspection / On-Site / performed nhưng không có sự kiện thông báo vi phạm cho người hưởng, dùng decide làm proxy là phải đoán nên không viết ràng buộc.*
- **gemini**: Không · — · tham chiếu: — · Cao · *Khoản này quy định phải thông báo cho người thụ hưởng về mọi vi phạm tuân thủ chéo được xác định trong vòng 3 tháng sau ngày kiểm tra tại chỗ, nhưng log không có sự kiện thông báo kết quả kiểm tra tuân thủ chéo cho nông dân.*

### R1306:Art99(4)

> 4. In any event, the total amount of reductions and exclusions for one calendar year shall not be more than the total amount referred to in the first subparagraph of paragraph 1.

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Trần tổng giảm trừ ≤ tổng chi trả trong năm (Art99(1)); log có case:penalty_amount0 và case:amount_applied0 nhưng đây là so sánh số tiền giữa thuộc tính, không biểu diễn được bằng mẫu DECLARE theo activity, và penalty_amount không chỉ là phạt cross-compliance.*
- **gemini**: Không · — · tham chiếu: — · Cao · *Khoản này giới hạn tổng số tiền giảm trừ và loại trừ do vi phạm tuân thủ chéo trong một năm không vượt quá tổng số tiền thanh toán được cấp, nhưng log không tách riêng số tiền phạt tuân thủ chéo với các khoản phạt khác.*

### R1307:Art62(1)

> 1. Farmers wishing to participate in the small farmers scheme shall submit an application by a date to be fixed by Member States which shall not be later than 15 October 2015. The date fixed by Member States cannot, however, be earlier than the last day for submitting an application under the basic payment scheme or the single area payment scheme. Farmers who have not applied to participate in the small farmers scheme on the date fixed by the Member State, who decide to withdraw from it after that date or who have been selected for support under point (c) of Article 19(1) of Regulation (EU) No…

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Hạn nộp đơn tham gia small farmers scheme (không muộn hơn 15/10/2015) là nghĩa vụ nông dân, nhưng log không có activity riêng cho đơn tham gia chương trình nông dân nhỏ (chỉ có cờ case:small farmer); dùng Payment application / Application / mail income làm proxy là đoán, nên không viết ràng buộc.*
- **gemini**: Không · — · tham chiếu: — · TB · *Khoản này quy định nông dân muốn tham gia chương trình nông dân nhỏ phải nộp đơn chậm nhất vào ngày 15/10/2015, nhưng log không có sự kiện riêng cho việc nộp đơn tham gia chương trình nông dân nhỏ (chỉ có đơn chung nộp trước tháng 5).*

### R809:Art34(1)

> 1. Applications or applicants found not to be admissible or not eligible for payment at the time of submission or after administrative checks shall not form part of the control population.

- **claude-opus-5-5**: Không chắc · — · tham chiếu: — · Thấp · *Hồ sơ không hợp lệ/không đủ điều kiện không được vào tập mẫu kiểm tra (khoản thuộc phần phát triển nông thôn); log không có sự kiện xác định "không hợp lệ khi nộp/sau kiểm tra hành chính" — case:rejected không rõ thời điểm và lý do, dùng làm proxy là đoán.*
- **gemini**: Có · Absence(Inspection / On-Site / initialize) | case:rejected == True · tham chiếu: Không · Thấp · *Các đơn hoặc người nộp đơn bị xác định là không hợp lệ hoặc không đủ điều kiện nhận thanh toán thì không được đưa vào quần thể chọn mẫu kiểm tra (proxy: case:rejected == True ≈ đơn không đủ điều kiện thanh toán; proxy: Inspection / On-Site / initialize ≈ đưa vào diện kiểm tra tại chỗ).*

### R809:Art48(1)

> 1. Administrative checks shall be carried out on all applications for support, payment claims or other declarations required to be submitted by a beneficiary or a third party, and shall cover all elements that can be checked and are appropriate to be checked by means of administrative checks. The procedures shall require recording of the control work undertaken, the results of the verification and the measures taken in the event of discrepancies. ( 1 ) Commission Regulation (EC) No 792/2009 of 31 August 2009 laying down detailed rules for the Member States’ notification to the Commission of in…

- **claude-opus-5-5**: Không · — · tham chiếu: — · TB · *Kiểm tra hành chính mọi đơn hỗ trợ thuộc biện pháp phát triển nông thôn ngoài IACS (Title IV Ch. II R809), không phải chi trả trực tiếp trong log; nghĩa vụ ghi chép quy trình cũng không quan sát được.*
- **gemini**: Có · Existence(Control summary / Main / initialize) · tham chiếu: Không · Thấp · *Kiểm tra hành chính phải được thực hiện trên tất cả các đơn xin hỗ trợ, yêu cầu thanh toán và phải ghi nhận công việc kiểm soát đã thực hiện (proxy: Control summary / Main / initialize ≈ thực hiện và ghi nhận kiểm tra hành chính).*

### R809:Art49(1)

> 1. Member States shall organise on-the-spot checks on approved operations using an appropriate sampling basis. Those checks shall, to the extent possible, be carried out before the final payment is made for an operation.

- **claude-opus-5-5**: Không · — · tham chiếu: — · TB · *Kiểm tra tại chỗ đối với hoạt động phát triển nông thôn đã duyệt, "to the extent possible" trước lần chi cuối; không phải nghĩa vụ cứng và không thuộc phạm vi chi trả trực tiếp của log.*
- **gemini**: Có · Precedence(Inspection / On-Site / performed → Payment application / Application / finish payment) | case:selected_random == True; Precedence(Inspection / On-Site / performed → Payment application / Application / finish payment) | case:selected_risk == True · tham chiếu: Không · Thấp · *Các cuộc kiểm tra tại chỗ đối với các hồ sơ trong mẫu kiểm tra phải được thực hiện trước khi khoản thanh toán cuối cùng được chi trả (proxy: Inspection / On-Site / performed ≈ thực hiện kiểm tra tại chỗ; proxy: Payment application / Application / finish payment ≈ hoàn tất thanh toán cuối cùng).*

## Kiểm ngẫu nhiên (đồng thuận)

R1306:Art70(2), R1307:Art8(1), R1307:Art21(4), R1307:Art24(8), R1307:Art39(2), R640:Art8, R640:Art9(2), R640:Art30(2), R809:Art11(1), R809:Art32(1), R809:Art37(3), R809:Art39(3), R809:Art68(5), R809:Art73(2), R809:Art73(4), R1306:Art7(6), R1306:Art84(3), R1306:Art114, R1307:Art14(1), R1307:Art37(7)
