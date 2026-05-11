(ns app.views.revops.users
  (:require [reagent.core :as r]
            [re-frame.core :as rf]
            [clojure.string :as str]
            [app.ds.layout :as layout]
            [app.ds.modal :as modal]
            [app.ds.inputs :as inputs]
            [app.ds.buttons :as btn]
            [app.auth.subs]))

(def role-options
  [{:value "EV"      :label "EV (Executivo de Vendas)"}
   {:value "CN"      :label "CN (Consultor de Negócios)"}
   {:value "LIDER_VENDAS" :label "Líder de Vendas"}
   {:value "FINANCE" :label "Financeiro"}
   {:value "ADMIN"   :label "Admin (RevOps)"}])

(def cn-nivel-options
  [{:value "" :label "Selecione"}
   {:value "CN1" :label "CN1"}
   {:value "CN2" :label "CN2"}
   {:value "CN3" :label "CN3"}])

(def cn-porte-options
  [{:value "" :label "Selecione"}
   {:value "M" :label "M"}
   {:value "G+" :label "G+"}])

(defn- empty-form [] {:name "" :email "" :role "" :team_id "" :nivel "" :porte ""})

(defn- form-from-user [user-data]
  (merge (empty-form)
         (select-keys (or user-data {}) [:name :email :role :team_id :nivel :porte])
         (when (:team_id user-data) {:team_id (str (:team_id user-data))})))

(defn- initials [name]
  (let [parts (->> (str/split (or name "") #"\s+") (filter seq) (take 2))]
    (->> parts (map (fn [p] (subs p 0 1))) (apply str) str/upper-case)))

(defn- cn-profile-label [u]
  (when (= (:role u) "CN")
    (str (or (:nivel u) "sem nivel") " / " (or (:porte u) "sem porte"))))

(defn user-modal []
  (let [form (r/atom (empty-form))]
    (r/create-class
      {:component-did-mount
       (fn [this]
         (let [{:keys [user-data]} (-> this .-props .-argv second)]
           (reset! form (form-from-user user-data))))
       :reagent-render
       (fn [{:keys [open? on-close user-data teams]}]
         (let [editing? (some? (:id user-data))]
           [modal/modal {:open? open? :on-close on-close
                         :title (if editing? "Editar Usuário" "Novo Usuário") :size :md}
            [:div {:style {:display "flex" :flex-direction "column" :gap "16px"}}
             [inputs/input {:label "Nome" :value (:name @form) :required true
                            :on-change #(swap! form assoc :name %)}]
             [inputs/input {:label "E-mail" :value (:email @form) :type "email" :required true
                            :on-change #(swap! form assoc :email %)}]
             [inputs/select {:label "Role" :value (:role @form) :options role-options :required true
                             :on-change #(swap! form assoc :role %)}]
             [inputs/select {:label "Time"
                             :value (or (:team_id @form) "")
                             :options (into [{:value "" :label "Sem time"}]
                                            (map #(hash-map :value (str (:id %)) :label (:name %))
                                                 (or teams [])))
                             :on-change #(swap! form assoc :team_id %)}]
             (when (= (:role @form) "CN")
               [:div.form-grid.-tight
                [inputs/select {:label "Nivel do CN"
                                :value (or (:nivel @form) "")
                                :options cn-nivel-options
                                :required true
                                :on-change #(swap! form assoc :nivel %)}]
                [inputs/select {:label "Porte"
                                :value (or (:porte @form) "")
                                :options cn-porte-options
                                :required true
                                :on-change #(swap! form assoc :porte %)}]])
             [:div {:style {:display "flex" :gap "10px" :justify-content "flex-end"}}
              [btn/button {:variant :secondary :on-click on-close} "Cancelar"]
              [btn/button
               {:variant :primary
                :disabled (or (str/blank? (:name @form))
                              (str/blank? (:email @form))
                              (str/blank? (:role @form))
                              (and (= (:role @form) "CN")
                                   (or (str/blank? (:nivel @form))
                                       (str/blank? (:porte @form)))))
                :on-click (fn []
                            (let [payload (-> @form
                                              (update :team_id #(when-not (str/blank? %) %))
                                              (update :nivel #(when-not (str/blank? %) %))
                                              (update :porte #(when-not (str/blank? %) %)))
                                  payload (if (= (:role payload) "CN")
                                            payload
                                            (assoc payload :nivel nil :porte nil))]
                              (if editing?
                                (rf/dispatch [:revops/update-user (:id user-data) (dissoc payload :email)])
                                (rf/dispatch [:revops/create-user payload])))
                            (on-close))}
               (if editing? "Salvar" "Criar")]]]]))})))

(defn users-page []
  (rf/dispatch [:revops/fetch-users])
  (rf/dispatch [:revops/fetch-teams])
  (let [modal-open?  (r/atom false)
        editing-user (r/atom nil)
        confirm-open?(r/atom false)
        confirm-row  (r/atom nil)
        active-role  (r/atom nil)
        search-text  (r/atom "")]
    (fn []
      (let [users     @(rf/subscribe [:revops/users])
            teams     @(rf/subscribe [:revops/teams])
            loading?  @(rf/subscribe [:revops/users-loading?])
            user      @(rf/subscribe [:auth/current-user])
            route     @(rf/subscribe [:current-route-name])
            counts    (frequencies (map :role (or users [])))
            q         (-> @search-text (or "") str/lower-case)
            shown     (cond->> (or users [])
                        @active-role  (filter #(= (:role %) @active-role))
                        (seq q)       (filter (fn [u]
                                                 (or (str/includes? (-> (:name u) (or "") str/lower-case) q)
                                                     (str/includes? (-> (:email u) (or "") str/lower-case) q)))))]
        [layout/page-shell
         {:current-route route :user user
          :crumbs ["plataforma rv" "configuração" "usuários"]
          :title "Usuários"
          :subtitle (str (count users) " ativo" (when (not= 1 (count users)) "s"))
          :header-actions
          [[:div.search
            [layout/icon "search" {:width 14 :height 14}]
            [:input {:placeholder "Nome, e-mail…"
                     :value @search-text
                     :on-change #(reset! search-text (.. % -target -value))}]]
           [:button.btn.btn-primary
            {:on-click #(do (reset! editing-user nil) (reset! modal-open? true))}
            [layout/icon "plus" {:width 14 :height 14}] "Convidar usuário"]]}

         [:div.filter-row {:role "group" :aria-label "Filtrar por papel"}
          [:button {:type "button"
                    :class (str "chip" (when (nil? @active-role) " active"))
                    :aria-pressed (str (nil? @active-role))
                    :on-click #(reset! active-role nil)}
           (str "Todos (" (count users) ")")]
          (for [role ["EV" "CN" "LIDER_VENDAS" "FINANCE" "ADMIN"]]
            ^{:key role}
            [:button {:type "button"
                      :class (str "chip" (when (= @active-role role) " active"))
                      :aria-pressed (str (= @active-role role))
                      :on-click #(reset! active-role role)}
             (str role " (" (or (counts role) 0) ")")])]

         [:div.card {:style {:padding 0}}
          [:table.table
           [:thead
            [:tr
             [:th "Usuário"]
             [:th "E-mail"]
             [:th "Perfil"]
             [:th "CN"]
             [:th "Time"]
             [:th "Status"]
             [:th.right "Ações"]]]
           [:tbody
            (cond
              loading?
              [:tr [:td {:col-span 7 :style {:padding "32px" :text-align "center" :color "var(--fg-3)"}}
                    "Carregando…"]]

              (empty? shown)
              [:tr [:td {:col-span 7 :style {:padding "48px" :text-align "center" :color "var(--fg-3)"}}
                    "Nenhum usuário encontrado"]]

              :else
              (for [u shown]
                ^{:key (:id u)}
                [:tr
                 [:td
                  [:div {:style {:display "flex" :gap "10px" :align-items "center"}}
                   [:div.avatar {:style {:width "28px" :height "28px" :font-size "11px"}}
                    (initials (:name u))]
                   [:div.name (:name u)]]]
                 [:td.muted (:email u)]
                 [:td [:span.badge.badge-locked (:role u)]]
                 [:td (or (cn-profile-label u) "·")]
                 [:td (or (:team_name u) "·")]
                 [:td [:span.badge.badge-approved "Ativo"]]
                 [:td.right
                  [:button.btn.btn-ghost.btn-sm
                   {:on-click #(do (reset! editing-user u) (reset! modal-open? true))}
                   [layout/icon "edit" {:width 12 :height 12}]]
                  " "
                  [:button.btn.btn-danger.btn-sm
                   {:on-click #(do (reset! confirm-row u) (reset! confirm-open? true))}
                   "Remover"]]]))]]]

         ^{:key (str "user-modal-" (or (:id @editing-user) "new") "-" @modal-open?)}
         [user-modal {:open? @modal-open? :on-close #(reset! modal-open? false)
                      :user-data @editing-user :teams teams}]

         [modal/confirm-dialog
          {:open? @confirm-open?
           :on-close #(reset! confirm-open? false)
           :on-confirm (fn []
                         (when-let [row @confirm-row]
                           (rf/dispatch [:revops/delete-user (:id row)]))
                         (reset! confirm-open? false))
           :title "Confirmar remoção"
           :message (str "Remover " (:name @confirm-row) "?")
           :confirm-label "Remover"
           :variant :danger}]]))))
