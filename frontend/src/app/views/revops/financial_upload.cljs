(ns app.views.revops.financial-upload
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.inputs :as inputs]
            [app.auth.subs]))

;; Upload Financeiro — design's dropzone + history table.

(defn- fmt-int [v]
  (when v (.toLocaleString (js/Math.round (if (string? v) (js/parseFloat v) v)) "pt-BR")))

(defn- upload-result-stats [result]
  (let [stats (or (:stats result) {})]
    [:div.callout {:style {:border-color "var(--success-light)" :background "var(--success-lightest)"}}
     [layout/icon "check" {:width 20 :height 20}]
     [:div {:style {:flex 1}}
      [:strong (str "Upload concluído — " (or (:rows_persisted result) 0) " linhas persistidas")]
      [:p {:style {:font-size "13px" :color "var(--fg-3)" :margin-top "2px"}}
       (str/join " · "
                 (for [[k label] [[:total_lidas "lidas"] [:persistidas "persistidas"]
                                  [:descartadas_status "status ≠ RECEBIDO"]
                                  [:descartadas_periodo "fora do período"]
                                  [:descartadas_vazias "vazias"]]
                       :let [v (get stats k 0)]
                       :when (some? v)]
                   (str (or v 0) " " label)))]]]))

(defn- upload-form []
  (let [form (r/atom {:quarter 1 :year 2026 :file nil})]
    (fn [{:keys [on-file kind]}]
      [:div {:style {:display "flex" :flex-direction "column" :gap "20px"}}
       [:div {:style {:display "flex" :gap "12px"}}
        [:div {:style {:width "150px"}}
         [inputs/select
          {:label "Trimestre"
           :value (str (:quarter @form))
           :options [{:value "1" :label "Q1"} {:value "2" :label "Q2"}
                     {:value "3" :label "Q3"} {:value "4" :label "Q4"}]
           :on-change #(swap! form assoc :quarter (js/parseInt %))}]]
        [:div {:style {:width "150px"}}
         [inputs/select
          {:label "Ano"
           :value (str (:year @form))
           :options [{:value "2024" :label "2024"} {:value "2025" :label "2025"}
                     {:value "2026" :label "2026"} {:value "2027" :label "2027"}]
           :on-change #(swap! form assoc :year (js/parseInt %))}]]]

       [:label.dropzone
        [:input {:type "file"
                 :accept ".xlsx,.xls,.csv"
                 :style {:display "none"}
                 :on-change (fn [e]
                              (let [f (-> e .-target .-files (aget 0))]
                                (when f
                                  (swap! form assoc :file f)
                                  (when on-file
                                    (on-file f (:quarter @form) (:year @form))))))}]
        [layout/icon "upload" {:width 36 :height 36}]
        [:strong "Solte os arquivos aqui ou clique para selecionar"]
        [:p {:style {:font-size "12px" :max-width "340px"}}
         (case kind
           :perks "Aceitamos XLSX com Cliente Pipo, Valor, Mês (Competência) e Ano. Re-upload substitui os subsídios existentes do trimestre."
           "Aceitamos CSV, XLSX, PDF (NFs). Máx. 50MB por arquivo. Os campos serão validados antes do processamento.")]
        [:button.btn.btn-primary.btn-sm {:style {:margin-top "8px"}}
         "Selecionar arquivos"]]])))

(defn financial-upload-page []
  (let [active-tab (r/atom :all)]
    (fn []
      (let [result       @(rf/subscribe [:revops/upload-result])
            loading?     @(rf/subscribe [:revops/upload-loading?])
            perk-result  @(rf/subscribe [:revops/perk-upload-result])
            perk-loading? @(rf/subscribe [:revops/perk-upload-loading?])
            user         @(rf/subscribe [:auth/current-user])
            route        @(rf/subscribe [:current-route-name])
            ;; Design fallback for the history table.
            history [{:file "nfs_junho_2026.csv"        :type "NFs"      :user "Lucas Pereira" :date "30/06/2026 14:22" :rows 1842 :status "approved"}
                     {:file "comissoes_q2_revops.xlsx"  :type "Comissão" :user "Ana Souza"     :date "29/06/2026 11:08" :rows 312  :status "approved"}
                     {:file "nfs_maio_2026.csv"          :type "NFs"      :user "Lucas Pereira" :date "31/05/2026 16:50" :rows 1798 :status "approved"}
                     {:file "comissoes_q1_revops.xlsx"  :type "Comissão" :user "Ana Souza"     :date "15/05/2026 09:30" :rows 294  :status "review"}
                     {:file "nfs_abril_2026.csv"         :type "NFs"      :user "Lucas Pereira" :date "30/04/2026 18:11" :rows 1756 :status "contested"}]
            shown (case @active-tab
                    :ok      (filter #(= (:status %) "approved") history)
                    :error   (filter #(= (:status %) "contested") history)
                    history)]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "operação" "upload financeiro"]
          :title "Upload Financeiro"
          :subtitle "NFs e comprovantes · Q2/2026"
          :header-actions
          [[:button.btn.btn-secondary
            [layout/icon "download" {:width 14 :height 14}] "Modelo CSV"]]}

         (cond
           loading?
           [:div.dropzone
            [layout/icon "refresh" {:width 36 :height 36 :class "spin"}]
            [:strong "Processando arquivo…"]]

           result
           [upload-result-stats result]

           :else
           [upload-form
            {:kind :financial
             :on-file (fn [f q y]
                        (rf/dispatch [:revops/upload-financial f q y]))}])

         [:div.card
          [:div.card-head
           [:div [:h3 "Subsídios / Perks"]
            [:div.card-sub "Soma por cliente, descontada das NFs na apuração"]]]
          (cond
            perk-loading?
            [:div {:style {:padding "32px" :text-align "center" :color "var(--fg-3)"}} "Processando subsídios…"]
            perk-result
            [:div.callout {:style {:border-color "var(--success-light)" :background "var(--success-lightest)"}}
             [layout/icon "check" {:width 20 :height 20}]
             [:div {:style {:flex 1}}
              [:strong (str "Subsídios aplicados — " (count (or (:items perk-result) [])) " clientes")]]]
            :else
            [upload-form
             {:kind :perks
              :on-file (fn [f q y]
                         (rf/dispatch [:revops/upload-perks f q y]))}])]

         [:div.card {:style {:padding 0}}
          [:div {:style {:padding "18px 20px 0" :display "flex" :justify-content "space-between" :align-items "flex-end"}}
           [:div [:h3 "Histórico de uploads"] [:div.card-sub "Últimos 30 dias"]]
           [:div.filter-row
            [:div {:class (str "chip" (when (= @active-tab :all) " active"))
                   :on-click #(reset! active-tab :all)} "Todos"]
            [:div {:class (str "chip" (when (= @active-tab :ok) " active"))
                   :on-click #(reset! active-tab :ok)} "Processados"]
            [:div {:class (str "chip" (when (= @active-tab :error) " active"))
                   :on-click #(reset! active-tab :error)} "Com erro"]]]
          [:table.table
           [:thead
            [:tr
             [:th "Arquivo"] [:th "Tipo"] [:th "Enviado por"] [:th "Data"]
             [:th.center "Linhas"] [:th "Status"] [:th.right "Ações"]]]
           [:tbody
            (for [r shown]
              ^{:key (:file r)}
              [:tr
               [:td.name.num (:file r)]
               [:td (:type r)]
               [:td (:user r)]
               [:td.num.muted (:date r)]
               [:td.center.num (or (fmt-int (:rows r)) "—")]
               [:td (case (:status r)
                      "approved"  [:span.badge.badge-approved "Processado"]
                      "review"    [:span.badge.badge-review "Em revisão"]
                      "contested" [:span.badge.badge-contested "Erro"]
                      [:span.badge.badge-locked (:status r)])]
               [:td.right
                [:button.btn.btn-ghost.btn-sm
                 [layout/icon "eye" {:width 12 :height 12}]]]])]]]]))))
